from project.server import init_celery

app = init_celery()
app.conf.imports = app.conf.imports + ("project.tasks",)
