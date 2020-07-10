"""
This is place for all admin views.

Views should ALWAYS extend ProtectedModelView !

"""
from flask import redirect, url_for, request, flash, abort, send_from_directory, current_app
from flask_admin import expose, helpers, AdminIndexView, BaseView
from flask_admin.actions import action
from flask_admin.contrib.rediscli import RedisCli
from flask_admin.contrib.sqla import ModelView as _ModelView
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import FlushError

from project.server import flask_admin as admin, db
from project.server.models import Customer, MailLog, Shop, Order, Device, Manufacturer, Repair, Image, DeviceSeries
# Create customized model view class
from .column_formatters import customer_formatter, link_to_device_formatter
from .forms import LoginForm, ChangePasswordForm, ImportRepairForm
from ..common.import_repair import import_repairs
from ..extensions import redis_client
from ..models.device import Color
from ..models.misc import MiscInquiry


class ProtectedBaseView(BaseView):

    def is_accessible(self):
        """ All admin views require authentication """
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        """
        Redirect to login page if user doesn't have access
        """
        return redirect(url_for('admin.login_view', next=request.url))

    def _handle_view(self, name, **kwargs):
        """
        Override builtin _handle_view in order to redirect users when a view is not accessible.
        """
        if not self.is_accessible():
            if current_user.is_authenticated:
                abort(403)
            else:
                return redirect(url_for('admin.login_view', next=request.url))


class ProtectedModelView(_ModelView, ProtectedBaseView):
    """ Secured Model View """
    pass


class RedisView(RedisCli, ProtectedBaseView):
    """ Secured Redis View """
    pass


class ProtectedIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        """ Render the welcome page for the admin """
        if not current_user.is_authenticated:
            return redirect(url_for('.login_view'))
        return super(ProtectedIndexView, self).index()

    @expose('/login/', methods=('GET', 'POST'))
    def login_view(self):
        """ Logic to handle a user logging in """
        form = LoginForm(request.form)
        if helpers.validate_form_on_submit(form):
            user = form.get_user()
            if user:
                login_user(user)
            else:
                flash("Invalid Credentials")

        if current_user.is_authenticated:
            return redirect(url_for('.index'))

        self._template_args['form'] = form
        return super(ProtectedIndexView, self).index()

    @expose('/password/', methods=('GET', 'POST'))
    def change_password_view(self):
        """ Logic for updating a password """
        if not current_user.is_authenticated:
            abort(403)

        form = ChangePasswordForm(request.form)
        if helpers.validate_form_on_submit(form):
            current_user.password = form.new_password.data
            current_user.save()
            logout_user()
            flash("Password updated successfully. Please login again.", "success")
            return redirect(url_for('.login_view'))

        self._template_args['form'] = form
        return self.render('admin/password.html')

    @expose('/logout/')
    def logout_view(self):
        """ Logout """
        logout_user()
        return redirect(url_for('.index'))


class AdminExportableModelView(ProtectedModelView):
    """ This just enables the export option """
    can_export = True
    can_view_details = True
    details_modal = True


class UserModelView(AdminExportableModelView):
    """ User List + Creation """
    column_exclude_list = ['password_hash', ]


class CustomerListView(AdminExportableModelView):
    """ Customers are only listed and can be edited but not created """
    can_create = False

    column_editable_list = ['first_name', 'last_name', 'street', 'zip_code', 'city', 'tel', 'email']


class MailLogView(AdminExportableModelView):
    """ Mail logs are generated by celery and should be changed or created """
    can_create = False
    can_edit = False
    can_delete = False

    def get_query(self):
        return self.model.query.order_by(self.model.timestamp.desc())


class ShopView(AdminExportableModelView):
    """ Shop list view """
    form_excluded_columns = ['orders']

    column_editable_list = ['name']


class OrderView(AdminExportableModelView):
    """ View all orders """
    can_create = False
    can_edit = True

    column_hide_backrefs = False

    # Create a direct href to customer details
    column_formatters = dict(customer=customer_formatter)


class SubmittedOrderView(OrderView):
    """ Submitted Orders """
    can_delete = False

    column_list = ('timestamp', 'kva', 'shop', 'color', 'customer', 'repairs', 'problem_description', 'customer_wishes_shipping_label')
    column_labels = {
        'timestamp': 'Zeitstempel',
        'kva': 'Kostenvoranschlag',
        'shop': 'Shop',
        'color': 'Farbe',
        'customer': 'Kunde',
        'repairs': 'Reparatur(en)',
        'problem_description': 'Problembeschreibung',
        'customer_wishes_shipping_label': 'Versandlabel erwünscht',
    }

    def get_query(self):
        return self.session.query(self.model).filter(self.model.complete == True).order_by(self.model.timestamp.desc())  # noqa


class PendingOrderView(OrderView):
    """ Not submitted orders """
    list_template = "admin/order/pending.html"
    can_delete = True

    column_list = ('timestamp', 'color', 'customer', 'repairs', 'problem_description')

    def get_query(self):
        return self.session.query(self.model).filter(self.model.complete == False).order_by(self.model.timestamp.desc())  # noqa


class DeviceView(AdminExportableModelView):
    """ Create and manage devices """
    form_excluded_columns = ['orders', 'repairs']

    column_default_sort = ("order_index", False)
    column_list = ('manufacturer', 'series', 'name', 'image', 'is_tablet', 'colors', 'order_index')
    column_filters = ('series.name', 'series.manufacturer.name')
    column_labels = {'series.name': 'Serie', 'series.manufacturer.name': 'Hersteller'}
    column_editable_list = ['series', 'image', 'is_tablet', 'name', 'colors']

    @action(
        "merge",
        "Zusammenführen",
        "Bist du sicher, dass du die gewählten Geräte mergen willst?"
    )
    def action_approve(self, ids):
        try:
            merger = Device.merge(ids)
        except (IntegrityError, FlushError)as e:
            flash("Zusammenführen fehlgeschlagen", "danger")
            current_app.logger.error(e)
            return
        except IndexError:
            flash("Bitte wähle mindestens 1 Gerät aus.")
            return
        flash(f"Die Geräte wurden erfolgreich zu {merger.name} zusammengeführt. Bitte passe den Namen an und prüfe die Bilder.")
        return redirect(url_for('device.edit_view', id=merger.id))

    @action(
        "normalize",
        "Normalisieren",
        "Sollen die ausgewählten Elemente normalisiert werden?",
    )
    def action_normalize(self, ids):
        selected = self.model.query.filter(self.model.id.in_(ids)).order_by(
            self.model.order_index
        )
        for i, model in enumerate(selected):
            model.order_index = i
            model.save()
        return redirect(url_for(".index_view"))

    @action(
        "normalize_by_name",
        "Normalisieren nach Name",
        "Sollen die ausgewählten Elemente nach ihrem Namen normalisiert werden?",
    )
    def action_normalize_by_name(self, ids):
        selected = self.model.query.filter(self.model.id.in_(ids)).order_by(
            self.model.name.desc()
        )

        for i, model in enumerate(selected):
            model.order_index = i
            model.save()

        return redirect(url_for(".index_view"))

    @action(
        "move_up",
        "Nach oben bewegen",
        "Sollen die ausgewählten Elemente nach oben verschoben werden?",
    )
    def action_move_up(self, ids):
        selected = self.model.query.filter(self.model.id.in_(ids)).order_by(
            self.model.order_index
        )
        for item in selected:
            item.move_up()
        return redirect(url_for(".index_view"))

    @action(
        "move_down",
        "Nach unten bewegen",
        "Sollen die ausgewählten Elemente nach unten verschoben werden?",
    )
    def action_move_down(self, ids):
        selected = self.model.query.filter(self.model.id.in_(ids)).order_by(
            self.model.order_index.desc()
        )
        for item in selected:
            item.move_down()
        return redirect(url_for(".index_view"))


class ColorView(AdminExportableModelView):
    """ Create and manage colors """
    form_excluded_columns = ['devices']

    column_editable_list = ['name', 'color_code']


class ManufacturerView(AdminExportableModelView):
    """ Create and manage manufacturers """
    form_excluded_columns = ['series']

    column_editable_list = ['name', 'image', 'activated']


class DeviceSeriesView(AdminExportableModelView):
    """ Series view """
    form_excluded_columns = ['devices']

    column_editable_list = ['name', 'manufacturer']


class RepairView(AdminExportableModelView):
    """ Repair View """
    form_excluded_columns = ['orders']
    form_widget_args = {
        'image': {
        }
    }

    column_sortable_list = ['device.name', 'name', 'image', 'price']
    column_editable_list = ['device', 'name', 'price', 'image']
    column_list = ['device.name', 'name', 'price', 'image']
    column_labels = {'device.name': 'Gerät'}
    column_filters = ('device.name', 'name', 'price')

    column_formatters = {'device.name': link_to_device_formatter}


class ImageView(AdminExportableModelView):
    """ Manage and view images  """
    form_excluded_columns = ['path']

    column_editable_list = ['name', 'device_default', 'tablet_default', 'repair_default', 'manufacturer_default']


class ImportView(ProtectedBaseView):
    @expose('/', methods=['GET', 'POST'])
    def index(self):
        form = ImportRepairForm()
        if form.validate_on_submit():
            f = request.files[form.repair_file.name]
            # store the file contents as a string
            fstring = f.read().decode('iso-8859-1')
            count, err_msg = import_repairs(fstring)
            if not count:
                flash(err_msg, "danger")
            else:
                flash(f"Import erfolgreich. Es wurden {count} Reparatruren erstellt")

        self._template_args['form'] = form
        return self.render('admin/import/import.html')

    @expose('/sample', methods=['GET'])
    def sample_csv(self):
        return send_from_directory('../data/', 'sample_csv.csv')


class MiscEnquiryView(ProtectedModelView):
    """ Misc enquiries """
    # Make customer col clickable and redirect to customer object
    column_formatters = dict(customer=customer_formatter)

    can_create = False


# Register ModelViews
admin.add_view(CustomerListView(Customer, db.session, name="Kunden"))  # Customer
admin.add_view(SubmittedOrderView(Order, db.session, name="Aufträge", endpoint="orders"))  # Orders
admin.add_view(PendingOrderView(Order, db.session, name="Nicht abgeschlossene Aufträge", endpoint="pending"))  # Orders
admin.add_view(MiscEnquiryView(MiscInquiry, db.session, name="Anfragen"))  # Misc

admin.add_view(ManufacturerView(Manufacturer, db.session, name="Hersteller"))  # Manufacturers
admin.add_view(DeviceSeriesView(DeviceSeries, db.session, name="Serien"))  # Manufacturers
admin.add_view(DeviceView(Device, db.session, name="Geräte"))  # Devices
admin.add_view(RepairView(Repair, db.session, name="Reparaturen"))  # Repairs

admin.add_view(ShopView(Shop, db.session, name="Shops"))  # Shop
admin.add_view(ColorView(Color, db.session, name="Farben"))  # Colors
admin.add_view(ImageView(Image, db.session, name="Bilder"))  # Images

admin.add_view(MailLogView(MailLog, db.session, name="Email Log"))  # Mails

admin.add_view(ImportView(name="Import"))  # Import View

admin.add_view(RedisView(redis_client.redis, name="Redis Konsole"))  # Redis view
