# Activate virtualenv
import settings
#activate_this = getattr(settings, 'VENV', None)
#if activate_this:
#    execfile(activate_this, dict(__file__=activate_this))
activate_this = getattr(settings, 'VENV', None)
with open(activate_this) as file_:
    exec(file_.read(), dict(__file__=activate_this))

from digimarks import app as application

if __name__ == "__main__":
    # application is ran standalone
    application.run(debug=settings.DEBUG)
