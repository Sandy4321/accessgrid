#!/usr/bin/python
#-----------------------------------------------------------------------------
# Name:        AGServiceManager.py
# Purpose:     
# Created:     2003/08/02
# RCS-ID:      $Id: AGServiceManager.py,v 1.61 2006-01-26 08:42:52 turam Exp $
# Copyright:   (c) 2002-2003
# Licence:     See COPYING.txt
#-----------------------------------------------------------------------------
import sys

import signal, time, os
from optparse import Option

# Our imports
from AccessGrid import Log
from AccessGrid.hosting import SecureServer, InsecureServer
from AccessGrid.Toolkit import Service
from AccessGrid import Toolkit
from AccessGrid.Platform import IsLinux
from AccessGrid.Platform.Config import AGTkConfig, SystemConfig
from AccessGrid.AGServiceManager import AGServiceManager
from AccessGrid.interfaces.AGServiceManager_interface import AGServiceManager as AGServiceManagerI
from AccessGrid.AGNodeService import AGNodeService
from AccessGrid.interfaces.AGNodeService_interface import AGNodeService as AGNodeServiceI
from AccessGrid import ServiceDiscovery

# default arguments
log = None
running = 0
gServiceManager = None
gNodeService = None

# Signal handler to shut down cleanly
def SignalHandler(signum, frame):
    """
    SignalHandler catches signals and shuts down the VenueServer (and
    all of it's Venues. Then it stops the hostingEnvironment.
    """
    global log, gServiceManager, gNodeService, running

    log.info("Caught signal, going down.")
    log.info("Signal: %d Frame: %s", signum, frame)

    gServiceManager.Shutdown()

    if gNodeService is not None:
        gNodeService.Stop()
        
    running = 0
    
def main():

    global gServiceManager, gNodeService, log, running

    # Create the app
    app = Service.instance()
    
    # build options for this application
    portOption = Option("-p", "--port", type="int", dest="port",
                        default=11000, metavar="PORT",
                        help="Set the port the service manager should run on.")
    app.AddCmdLineOption(portOption)
    nsOption = Option("-n", "--nodeService", action="store_true", dest="nodeService",
                        help="Run a node service interface too.")
    app.AddCmdLineOption(nsOption)
    
    # Initialize the application
    try:
        app.Initialize(Log.ServiceManager)
    except Exception, e:
        print "Toolkit Initialization failed, exiting."
        print " Initialization Error: ", e
        sys.exit(-1)


    log = app.GetLog()
    Log.SetDefaultLevel(Log.ServiceManager, Log.DEBUG)

    port = app.GetOption("port")
        
    # Create the hosting environment
    hostname = app.GetHostname()
    if app.GetOption("secure"):
        context = Toolkit.GetDefaultApplication().GetContext()
        server = SecureServer((hostname, port), context)
    else:
        server = InsecureServer((hostname, port))

    # Create the Service Manager
    gServiceManager = AGServiceManager(server)
    
    # Create the Service Manager Service
    smi = AGServiceManagerI(impl=gServiceManager,auth_method_name=None)
    server.RegisterObject(smi,path="/ServiceManager")
    url = server.FindURLForObject(gServiceManager)
    gServiceManager.SetName('%s:%d' % (hostname,port))
    gServiceManager.SetUri(url)

    if app.GetOption("nodeService") is not None:
        # Create a Node Service
        gNodeService = AGNodeService()
        # Create the Node Service Service
        nsi = AGNodeServiceI(impl=gNodeService,auth_method_name=None)
        server.RegisterObject(nsi, path="/NodeService")
        nsurl = server.FindURLForObject(gNodeService)
        log.info("Starting Node Service URL: %s", nsurl)
        print "Starting Node Service URL:", nsurl
        
        # Add the service manager to the node service
        smdesc = gServiceManager.GetDescription()
        smdesc.builtin = 1
        gNodeService.serviceManagers[url] = smdesc
    
    # Register the signal handler so we can shut down cleanly
    signal.signal(signal.SIGINT, SignalHandler)

    if IsLinux():
        signal.signal(signal.SIGHUP, SignalHandler)

    # Start the service
    server.RunInThread()


    # Tell the world where to find the service manager
    log.info("Starting Service Manager URL: %s", url)
    print "Starting Service Manager URL:", url
    
    # Optionally load node configuration
    if app.GetOption("nodeService") and app.GetOption("configfilename"):
        nodeConfig = app.GetOption("configfilename")
        gNodeService.MigrateNodeConfig(nodeConfig)
        try:
            gNodeService.LoadConfiguration(nodeConfig)
        except Exception, e:
            print "Failed to load default node config", e

    # Advertise the service
    try:
        ServiceDiscovery.Publisher(hostname,AGServiceManager.ServiceType,
                                        url,port=port)
        if app.GetOption('nodeService'):
            ServiceDiscovery.Publisher(hostname,AGNodeService.ServiceType,
                                       nsurl,port=port)
    except:
        log.exception("Failure advertising service")
    
    # Keep the main thread busy so we can catch signals
    running = 1
    while running:
        try:
            time.sleep(1)
        except IOError, e:
            log.info("Sleep interrupted, exiting.")

    # Exit cleanly
    server.Stop()
    sys.exit(0)



if __name__ == "__main__":
    main()
