import imp
wsgi = imp.load_source("wsgi", "/home/dfvvjhl7/helix_tel/app.py")
application = wsgi.app
