
import os

dstPath = os.path.join("..", "cache")

if not os.path.exists(dstPath):
    os.mkdir(dstPath)

initFile = os.path.join(dstPath, "__init__.py")
if not os.path.exists(initFile):
    open(initFile, "w").close()

command = "wsdl2py.py -f VenueServerBinding.wsdl -e -d %s -t AccessGrid_Types" % dstPath
os.system(command)
command = "wsdl2dispatch.py -f VenueServerBinding.wsdl -e -d %s -t AccessGrid_Types" % dstPath
os.system(command)
command = "wsdl2dispatch.py -f VenueBinding.wsdl -e -d %s -t AccessGrid_Types" % dstPath
os.system(command)
command = "wsdl2py.py -f VenueBinding.wsdl -e -d %s -t AccessGrid_Types" % dstPath
os.system(command)
