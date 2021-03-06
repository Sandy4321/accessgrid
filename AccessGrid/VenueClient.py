#!/usr/bin/python
#-----------------------------------------------------------------------------
# Name:        VenueClient.py
# Purpose:     This is the client side object of the Virtual Venues Services.
# Created:     2002/12/12
# RCS-ID:      $Id: VenueClient.py,v 1.362 2007-11-29 11:31:44 willing Exp $
# Copyright:   (c) 2003
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------

"""
"""
__revision__ = "$Id: VenueClient.py,v 1.362 2007-11-29 11:31:44 willing Exp $"


import sys
import os
import string
import threading


import time
import socket
import urlparse

from AccessGrid import Log
from AccessGrid import DataStore
from AccessGrid import hosting
from AccessGrid import Version
from AccessGrid.Toolkit import Application, Service
from AccessGrid.Preferences import Preferences
from AccessGrid.Descriptions import Capability, STATUS_ENABLED, STATUS_DISABLED
from AccessGrid.Descriptions import BeaconSource, BeaconSourceData
from AccessGrid.Descriptions import BridgeDescription, QUICKBRIDGE_TYPE, UMTP_TYPE
from AccessGrid.Platform.Config import UserConfig, SystemConfig
from AccessGrid.Platform.ProcessManager import ProcessManager
from AccessGrid.Venue import ServiceAlreadyPresent, CertificateRequired
from AccessGrid.interfaces.Venue_client import VenueIW
from AccessGrid.hosting.SOAPInterface import SOAPInterface, SOAPIWrapper
from AccessGrid.hosting import InsecureServer, SecureServer
from AccessGrid.Utilities import LoadConfig, BuildServiceUrl
from AccessGrid.NetUtilities import GetSNTPTime
from AccessGrid.VenueClientObserver import VenueClientObserver
from AccessGrid.scheduler import Scheduler
from AccessGrid.VenueEventClient import VenueEventClient
from AccessGrid.Events import Event, ConnectEvent
from AccessGrid.Events import DisconnectEvent, ClientExitingEvent
from AccessGrid.Events import RemoveDataEvent, UpdateDataEvent
from AccessGrid.ClientProfile import ClientProfile, ClientProfileCache, InvalidProfileException
from AccessGrid.Descriptions import ApplicationDescription, ServiceDescription
from AccessGrid.Descriptions import DataDescription, DirectoryDescription, FileDescription, ConnectionDescription
from AccessGrid.Descriptions import NodeConfigDescription
from AccessGrid.interfaces.AGNodeService_client import AGNodeServiceIW
from AccessGrid.interfaces.AuthorizationManager_client import AuthorizationManagerIW
from AccessGrid.AGNodeService import AGNodeService
from AccessGrid import ServiceDiscovery
from AccessGrid.Descriptions import VenueState
from AccessGrid.MulticastWatcher import MulticastWatcher
from AccessGrid.Registry.RegistryClient import RegistryClient
from AccessGrid import QuickBridgeClient
from AccessGrid.BridgeCache import BridgeCache
from AccessGrid.VenueCache import VenueCache
from AccessGrid.NetworkLocation import MulticastNetworkLocation
from AccessGrid import UMTPClient
from AccessGrid.Platform import IsWindows, IsLinux, IsFreeBSD

from AccessGrid.GUID import GUID
from AccessGrid.Jabber.JabberClient import JabberClient, AuthorizationFailure

from AccessGrid.interfaces.AGService_client import AGServiceIW
from AccessGrid.interfaces.VenueClient_client import VenueClientIW
from AccessGrid.hosting import HostingException
from AccessGrid.hosting import GetHostingExceptionModuleAndClassName

# Force ZSI to use the M2Crypto HTTPSConnection as transport
from ZSI import client
from M2Crypto import httpslib
client.Binding.defaultHttpsTransport = httpslib.HTTPSConnection



try:
    from AccessGrid.Beacon.rtpBeacon import Beacon
except:
    pass
    
class EnterVenueException(Exception):
    pass
   
class AuthorizationFailedError(Exception):
    pass

class GetDataStoreInfoError(Exception):
    pass

class GetDataDescriptionsError(Exception):
    pass

class NotAuthorizedError(Exception):
    pass

class NetworkLocationNotFound(Exception):
    pass

class DisconnectError(Exception):
    pass

class UserWarning(Exception):
    pass


class NoServices(Exception):
    pass

log = Log.GetLogger(Log.VenueClient)
from AccessGrid.BridgeUtilities import TestBridges
class BridgePingThread(threading.Thread):
    """
    This is used to keep the bridge ping times up to date
    """
    def __init__(self, preferences, registryClient, bridges):
        self.preferences = preferences
        self.registryClient = registryClient
        self.bridges = bridges
        self.bridgesDone = 0
        threading.Thread.__init__ (self)
        self._running = threading.Event()
        self.refreshDelay = int(self.preferences.GetPreference(Preferences.BRIDGE_PING_UPDATE_DELAY))
        mcaddr = self.preferences.GetPreference(Preferences.MULTICAST_DETECT_HOST)
        mcport = int(self.preferences.GetPreference(Preferences.MULTICAST_DETECT_PORT))
        self.multicastTestLocation = MulticastNetworkLocation(mcaddr,mcport,1)
    
    def run(self):

        self._running.set()
        while self._running.isSet():    

            # wait for refresh time to expire, but wait incrementally to allow early exit
            self.refreshDelay = int(self.preferences.GetPreference(Preferences.BRIDGE_PING_UPDATE_DELAY))

            t = time.time()
            while time.time() - t < self.refreshDelay:
                if not self._running.isSet():
                    return
                time.sleep(0.1)

            try:
                # Ping the bridges to measure distance
                starttime = time.time()
                log.debug("Updating %d bridges" % (len(self.bridges)))
                TestBridges(self.bridges,self.multicastTestLocation)

                # Update the bridge list in the user preferences
                bridgeList = {}
                for b in self.bridges:
                    bridgeList[b.GetKey()] = b
                self.preferences.SetBridges(bridgeList)

                log.debug("Finished Updating Bridges (waiting %d seconds)" % (self.refreshDelay))
            except: 
                log.exception('Exception in BridgePingThread; continuing')
                
        log.info('BridgePingThread exiting')
    
    def PingBridge(self, b):
        try:
            self.registryClient.PingBridge(b)
        except:
            log.exception('Exception pinging bridge %s', b.host)
    
    def close(self):
        self._running.clear()

class VenueClient:
    """
    This is the client side object that maintains a stateful
    relationship with a Virtual Venue. This object provides the
    programmatic interface to the Access Grid for a Venues User
    Interface.  The VenueClient can only be in one venue at a    time.
    @group WebServiceMethods: EnterVenue,GetApplications,GetBeaconSourceData,GetBeaconSources,GetClientProfile,GetConnections,GetDataStoreUploadUrl,GetNodeServiceURL,GetServices,GetStreams,GetUsers,GetVenueData,GetVenueURL,GetVersion,IsValid
    """    
    ServiceType = '_venueclient._tcp'
    
    def __init__(self, profile=None, pnode=None, port=0, progressCB=None,
                 app=None,nodeConfigName=None):
        """
        This client class is used on shared and personal nodes.
        """
        self.jabberHost = None
        self.chatLocation= ''
        self.beacon = None
        self.userConf = UserConfig.instance()
        self.isPersonalNode = pnode
        self.nodeService = None
        self.dataStoreUploadUrl = None
        self.builtInNodeService = None
        self.builtInNodeServiceUri = ""
        self.bridgeCache = BridgeCache()
        self.bridgePinger = None
        self.__venueClientUI = None
        self.registryClient = None
        
        self.certRequired = 0
              
        if app is not None:
            self.app = app
        else:
            self.app = Application.instance()
            
        self.preferences = self.app.GetPreferences()
        self.preferences.SetVenueClient(self)
        self.profile = self.preferences.GetProfile()
       
        if pnode is None:
            pnode = int(self.preferences.GetPreference(Preferences.STARTUP_MEDIA))
            self.isPersonalNode = pnode
        else:
            # user specified a command-line value, so honor it
            self.isPersonalNode = pnode

        self.hostname = self.app.GetHostname()
        self.capabilities = []
        self.homeVenue = None
        self.houseKeeper = Scheduler()
        self.heartBeatTimer = None
        self.heartBeatCounter = 0
        self.jabberIdRetries = 0
        
        
        self.venueList = []
        venueServerUrls = self.preferences.GetPreference(Preferences.VENUESERVER_URLS)
        venueServerUrls = venueServerUrls.split('|')
        venuesFile = self.app.GetUserConfig().GetVenuesCache()
        self.venueCache = VenueCache(venuesFile,venueServerUrls)
        self.venueCache.Load()
      
        # if no venues cache exists, update sooner by using smaller initial delay
        if not self.venueCache.GetVenues(): 
            self.houseKeeper.AddTask(self.venueCache.Update, 300, 30)
        else:
            self.houseKeeper.AddTask(self.venueCache.Update, 300, 300)
        self.houseKeeper.StartAllTasks()

       
        self.__StartWebService(pnode, port)
        
        self.__InitVenueData()
        
        # Set nodeservice based on preferences
        try:
            builtin = int(self.preferences.GetPreference(Preferences.NODE_BUILTIN))
        except Exception, e:
            log.exception('preference NODE_BUILTIN is not an int: %s' % e)
            builtin = True
            
        if builtin:
            self.nodeServiceUri = self.builtInNodeServiceUri
            self.nodeService = self.builtInNodeService
        else:
            self.nodeServiceUri = self.preferences.GetPreference(Preferences.NODE_URL) 
            self.nodeService = AGNodeServiceIW(self.nodeServiceUri)

        self.isInVenue = 0
        self.isIdentitySet = 0

        self.streamDescList = []

        self.SetupBridgePrefs()

        if int(self.preferences.GetPreference(Preferences.MULTICAST)):   
            self.transport = "multicast"
        else:
            self.transport = "unicast"

        self.observers = []

        # Manage the currently-exiting state
        self.exiting = 0
        self.exitingLock = threading.Lock()

        self.venueUri = None
        self.__venueProxy = None
        self.__secondaryVenueProxy = None

        # Cache profiles in case we need to look at them later.
        # specifically, the cache makes it easier to add roles when
        # managing venues.
        self.profileCachePrefix = "profileCache"
        self.profileCachePath = os.path.join(self.userConf.GetConfigDir(),
                                             self.profileCachePrefix)
        self.cache = ClientProfileCache(self.profileCachePath)

        self.jabber = JabberClient()
        self.jabber.SetPresenceCB(self.JabberPresenceCB)
        self.maxJabberNameRetries = 3
        self.jabberNameRetries = 0
        self.textLocation = None

        try:
            mcdhost = self.preferences.GetPreference(Preferences.MULTICAST_DETECT_HOST)
            mcdport = self.preferences.GetPreference(Preferences.MULTICAST_DETECT_PORT)
            mcdport = int(mcdport)
            self.multicastWatcher = MulticastWatcher(mcdhost,mcdport)
        except:
            self.multicastWatcher = None
       
        self.beaconLocation = None

        # Create beacon capability
        self.beaconCapabilities = [Capability(Capability.PRODUCER, "Beacon", "ANY", 0, 1),
                                   Capability(Capability.CONSUMER, "Beacon", "ANY", 0, 1)]
            
    def BuildDefaultNodeConfiguration(self,nodeConfigName='default_auto',default=1):
        resources = self.sm.GetResources()
        
        # On Windows, skip old style (VFW) capture devices, as long as WDM capture devices exist
        if IsWindows():
            wdmresources = filter( lambda x: x.name != 'Microsoft WDM Image Capture (Win32)' , resources)
            if wdmresources:
                resources = wdmresources
        elif IsLinux() or IsFreeBSD():
            # on linux, skip the V4L and x11 capture devices
            resources = filter( lambda x: x.name != 'x11', resources)
            resources = filter( lambda x: x.name.startswith('V4L:') == False, resources)
            
        profile = self.preferences.GetProfile()
        
        if resources:
            self.sm.AddServiceByName('VideoService.zip',resources[0],config=[],identity=profile)
            for r in resources[1:]:
                self.sm.AddServiceByName('VideoProducerService.zip',r,config=[],identity=profile)
        else:
            self.sm.AddServiceByName('VideoConsumerService.zip',config=[],identity=profile)
            
        self.sm.AddServiceByName('AudioService.zip',config=[],identity=profile)
        
        nodeConfig = NodeConfigDescription(nodeConfigName,NodeConfigDescription.USER)
        self.builtInNodeService.StoreConfiguration(nodeConfig)
        if default:
            self.preferences.SetPreference(Preferences.NODE_CONFIG,nodeConfig.name)
      	    self.preferences.SetPreference(Preferences.NODE_CONFIG_TYPE,nodeConfig.type)
        self.preferences.StorePreferences()

    
    def SetupBridgePrefs(self):
        self.allowedUrlProtocols = ['file', 'http']
        self.bridges = self.preferences.GetBridges()
        self.currentBridge = None
        self.registryUrls = []
        regPrefs = self.preferences.GetPreference(Preferences.BRIDGE_REGISTRY).split('|')
        # Opportunity here to test validity of url.
        for regPrefsEntry in regPrefs:
            regUrl = regPrefsEntry.strip()
            parsedUrl = urlparse.urlparse(regUrl)
            for proto in self.allowedUrlProtocols:
                protoMatched = False
                if parsedUrl[0].endswith(proto):
                    protoMatched = True
                    break
            if protoMatched:
                self.registryUrls.append(regUrl)

    def LoadBridges(self, progressCB=None):
        '''
        Gets bridge information from bridge registry. Sets current
        bridge to the first one in the sorted list. Also, check preferences
        to see if any of the retreived bridges are disabled.
        '''
        if self.bridgePinger != None:
            self.bridgePinger.close()
            self.bridgePinger = None
        
        log.debug('get bridges from preferences')
        self.bridges = self.preferences.GetBridges()
        
        multicastAddr = self.preferences.GetPreference(Preferences.MULTICAST_DETECT_HOST)
        multicastPort = int(self.preferences.GetPreference(Preferences.MULTICAST_DETECT_PORT))
        multicastNetworkLocation = MulticastNetworkLocation(host=multicastAddr, port=multicastPort, ttl=1)
        multicastNetworkLocation.id = GUID()
        multicastNetworkLocation.privateId = GUID()
        multicastNetworkLocation.profile=("","")
        
        # for all the user's registries
        for registryUrl in self.registryUrls:
            try:
                log.debug("Trying bridge registry: %s" % registryUrl)
                self.registryClient = RegistryClient(url=registryUrl)
                if self.registryClient == None:
                    log.debug("Unable to connect with registry (%s); skipping", registryUrl)
                    continue
                
                # get bridges from the registry
                bridgeList = self.registryClient.LookupBridge()
                
                # find bridges new to the user
                newBridges = filter( lambda x: not self.bridges.has_key(x.GetKey()), bridgeList )
                
                # test new bridges only
                TestBridges(newBridges,multicastNetworkLocation,progressCB)
                for b in newBridges:
                    self.bridges[b.GetKey()] = b

            except:
                log.exception("LoadBridges: Can not connect to bridge registry %s ", registryUrl)
        
        # apply some artificial user rank.  WHY?
        bridgeList = self.bridges.values()
        bridgeList.sort(lambda x,y: BridgeDescription.sort(x, y, 0))
        for index in range(0, len(bridgeList)):
            bridgeList[index].userRank = float(index + 1)
        
        # update bridges in preferences
        self.preferences.SetBridges(self.bridges)
        self.preferences.StoreBridges()

        # probably don't need to do this
        self.currentBridge = self.FindBridge(bridgeList)
        
        # restart bridge pinger (was shut down above).  WHY SHUT DOWN AND RESTART ?
        self.bridgePinger = BridgePingThread(self.preferences, self.registryClient, bridgeList)
        self.bridgePinger.setDaemon(True)
        self.bridgePinger.start()
        
        return bridgeList


    def FindBridge(self, bridgeList):

        retBridge = None
                
        # sort the bridge list
        orderBridgesByPing = self.preferences.GetPreference(Preferences.ORDER_BRIDGES_BY_PING)
        bridgeList.sort(lambda x,y: BridgeDescription.sort(x, y, orderBridgesByPing))

        # use first enabled bridge in sorted list
        for b in bridgeList:

            if (b.status == STATUS_ENABLED):
                retBridge = b
                break

        return retBridge
                        

    ##########################################################################
    #
    # Private Methods

    def __InitVenueData( self ):
        self.eventClient = None
#        self.textClient = None
        self.venueState = None
        self.venueUri = None
        self.__venueProxy = None
        self.__secondaryVenueProxy = None
        #self.privateId = None


    def __CheckForInvalidClock(self):
        """
        Check to see if the local clock is out of synch, a common reason for a
        failed authentication.

        This routine only currently sets self.warningString, and should only be
        invoked from the TCPSocketException-handling code in EnterVenue.

        """

        timeserver = "ntp-1.accessgrid.org"
        timeout = 0.3
        maxOffset = 10

        try:
            serverTime = GetSNTPTime(timeserver, timeout)
        except:
            log.exception("__CheckForValideClock: Connection to sntp server at %s failed", timeserver)
            serverTime = None

        if serverTime is not None:

            diff = int(time.time() - serverTime)
            absdiff = abs(diff)

            if absdiff > maxOffset:

                if diff > 0:
                    direction = "fast"
                else:
                    direction = "slow"

                self.warningString = ("Authorization failure connecting to server. \n" + \
                                     "This may be due to the clock being incorrect on\n" + \
                                     "your computer: it is %s seconds %s with respect\n" + \
                                     "to the time server at %s.") % \
                                     (absdiff, direction, timeserver)
            else:
                #
                # Time is okay.
                #
                log.exception("__CheckForValideClock: failed; time is okay (offset=%s", diff)

                self.warningString = "Authorization failure connecting to server."
        else:
            self.warningString = "Authorization failure connecting to server. \n" + \
                                 "Please check the time on your computer; an incorrect\n" + \
                                 "local clock can cause authorization to fail."


    def __StartWebService(self, pnode, port):
        from AccessGrid.NetworkAddressAllocator import NetworkAddressAllocator
        if port == 0:
            if pnode:
                port = 11000
            else:
                port = NetworkAddressAllocator().AllocatePort()
                        
        try:
            self.server = InsecureServer((self.hostname, port))
        except socket.error:
            port = NetworkAddressAllocator().AllocatePort()
            self.server = InsecureServer((self.hostname, port))

        from AccessGrid.interfaces.VenueClient_interface import VenueClient as VenueClientI
        vci = VenueClientI(impl=self,auth_method_name=None)
        uri = self.server.RegisterObject(vci, path='/VenueClient')
        try:
            threading.Thread(target = ServiceDiscovery.Publisher,
                            args = (self.hostname,VenueClient.ServiceType,
                                        uri,port)).start()
        except:
            log.exception("Couldn't publish node service advertisement")


        if(self.profile != None):
            self.profile.venueClientURL = uri

        if pnode:
            from AccessGrid.AGServiceManager import AGServiceManager
            from AccessGrid.interfaces.AGServiceManager_interface import AGServiceManager as AGServiceManagerI
            self.sm = AGServiceManager(self.server, self.app)
            smi = AGServiceManagerI(impl=self.sm,auth_method_name=None)
            smuri = self.server.RegisterObject(smi, path="/ServiceManager")
            
            self.sm.SetUri(smuri)
            log.debug("__StartWebService: service manager: %s",
                      smuri)
            try:
                threading.Thread(target = ServiceDiscovery.Publisher,
                                 args=(self.hostname,AGServiceManager.ServiceType,
                                       smuri,port)).start()
            except:
                log.exception("Couldn't publish node service advertisement")

            from AccessGrid.AGNodeService import AGNodeService
            from AccessGrid.interfaces.AGNodeService_interface import AGNodeService as AGNodeServiceI
            ns = self.builtInNodeService = AGNodeService(self.app,builtInServiceManager=self.sm)
            nsi = AGNodeServiceI(impl=ns,auth_method_name=None)
            nsuri = self.builtInNodeServiceUri = self.server.RegisterObject(nsi, path="/NodeService")
            log.debug("__StartWebService: node service: %s",
                      nsuri)
            self.builtInNodeServiceUri = nsuri
            
            smdesc = self.sm.GetDescription()
            smdesc.builtin = 1
            self.builtInNodeService.serviceManagers[smuri] = smdesc
            
            try:
                threading.Thread(target = ServiceDiscovery.Publisher,
                                args = (self.hostname,AGNodeService.ServiceType,
                                        nsuri,port)).start()
            except:
                log.exception("Couldn't publish node service advertisement")
                
        self.server.RunInThread()

        # Save the location of the venue client url
        # for other apps to communicate with the venue client
        self.urlFile = os.path.join(UserConfig.instance().GetTempDir(),
                               "venueClientUrl%d" % (os.getpid()))
        try:
            fileH = open(self.urlFile,"w")
            fileH.write(self.GetWebServiceUrl())
            fileH.close()
        except:
            log.exception("Error writing web service url file")
        
    def __StopWebService(self):
    
        if self.isPersonalNode:
            self.nodeService.Stop()
            self.sm.Shutdown()
    
        # Stop the ws server
        if self.server:
            self.server.Stop()
            
        # Remove the file
        try:
            os.remove(self.urlFile)
        except:
            log.exception("Error removing url file %s", self.urlFile)
            
    def GetWebServiceUrl(self):
        return self.server.FindURLForObject(self)
        
    def Heartbeat(self):

        nextTimeout = 30
        try:
            log.debug("Calling Heartbeat, time now: %d", time.time())
            if self.heartBeatTimer is not None:
                self.heartBeatTimer.cancel()

            # Note:  heartbeat timeout is a dummy argument for now;
            #        remove it when 3.0 servers are no longer a concern
            dummyClientTimeout = 30
            nextTimeout = self.__secondaryVenueProxy.UpdateLifetime(
                self.profile.connectionId,dummyClientTimeout)
                
            if nextTimeout == -1:
                # server doesn't recognize client anymore; stop sending heartbeats
                log.info("VenueServer returned error on UpdateLifetime; stopping heartbeats")
                return
                
            ##
            ## CODE TO ACCOMMODATE 3.0 SERVER TIMEOUTS
            ## REMOVE WHEN 3.0 SERVER COMPAT IS NOT A CONCERN
            # 3.0 servers will return a 15-second timeout; we try
            # to accommodate them by sending a heartbeat after 5 
            # seconds, which is now considered too often
            if nextTimeout == 15:
                nextTimeout = 5
                
            log.debug("Next Heartbeat needed within %ds", nextTimeout)
            
        except Exception, e:
            log.exception("Error sending heartbeat; next heartbeat in %ds", nextTimeout)

        # Check jabber status by occasionally sending a presence stanza.
        # If that fails, we'll know a new jabber connection will be needed.
        # This also lets the jabber server know we're still alive, perhaps
        # preventing server side disconnections which we're trying to catch here.
        self.heartBeatCounter += 1
        log.debug("heartBeatCounter = %d", self.heartBeatCounter)
        if self.heartBeatCounter > 60:
            jabberRestartNeeded = False
            self.heartBeatCounter = 0
            try:
                self.jabber.SendPing()
            except Exception, e:
                log.exception("Couln't ping jabber: %s", e)
                jabberRestartNeeded = True
            if jabberRestartNeeded:
                log.info("Jabber restart needed")
                self.__RestartJabber()

        self.heartBeatTimer = threading.Timer(nextTimeout,
                                              self.Heartbeat)
        self.heartBeatTimer.start()

    def __Reconnect(self):
    
        """
        Reconnect to venue
        """
        numTries = 0

        log.info("Try to reconnect to venue")
        
        venueUri = self.venueUri
        # Client no longer in venue
        self.isInVenue = 0
        
        # Exit the venue (internally)
        try:
            self.__ExitVenue()
        except Exception:
            log.info("Exception exiting from venue before reconnect -- not critical")

        # Try to enter the venue
        while (not self.isInVenue and
               numTries < int(self.preferences.GetPreference(Preferences.MAX_RECONNECT)) and 
               int(self.preferences.GetPreference(Preferences.RECONNECT))): 
        
            try:
                self.__EnterVenue(venueUri)
                self.failedHeartbeats = 0
            
                # If we're connected, stop trying
                if self.isInVenue:
                    break
            except:
                log.exception("Exception reconnecting to venue")
            
            time.sleep(int(self.preferences.GetPreference(Preferences.RECONNECT_TIMEOUT)))
            numTries += 1

        if self.isInVenue:
            # Update observers
            
            for s in self.observers:
                s.ExitVenue()

            for s in self.observers:
                try:
                    # enterSuccess is true if we entered.
                    s.EnterVenue(venueUri)
                except:
                    log.exception("Exception in observer")

        else:
            log.info("Failed to reconnect")
            self.ExitVenue()
            for s in self.observers:
                s.HandleError(DisconnectError())

    # end Private Methods
    #
    ##########################################################################

    ##########################################################################
    #
    # Event Handlers

    def AddUserEvent(self, event):
        log.debug("AddUserEvent: Got Add User Event")

        profile = event.GetData()
        
        self.venueState.AddUser(profile)
        for s in self.observers:
            s.AddUser(profile)

    def RemoveUserEvent(self, event):
        log.debug("RemoveUserEvent: Got Remove User Event")

        profile = event.GetData()
        
        # Handle removal of self
        if profile.connectionId == self.profile.connectionId:
        
            updateNode = int(self.preferences.GetPreference(Preferences.SHUTDOWN_MEDIA))
        
            # Get out and stay out
            self.ExitVenue(updateNode=updateNode)
            for s in self.observers:
                s.HandleError(DisconnectError())
            return

        self.venueState.RemoveUser(profile)
        for s in self.observers:
            s.RemoveUser(profile)

        log.debug("RemoveUserEvent: Got Remove User Event...done")

    def ModifyUserEvent(self, event):
        log.debug("ModifyUserEvent: Got Modify User Event")
        profile = event.GetData()

        self.venueState.ModifyUser(profile)
        for s in self.observers:
            s.ModifyUser(profile)

    def AddDataEvent(self, event):
        log.debug("AddDataEvent: Got Add Data Event")
          
        data = event.GetData()
      
        if data.GetType() == "None" or data.GetType() == None:
            # Venue data gets saved in venue state
            self.venueState.AddData(data)
                      
        for s in self.observers:
            s.AddData(data)
            
    #Added by NA2-HPCE
    def AddDirEvent(self, event):
        log.debug("AddDirEvent:Entered AddDirEvent!")
        data = event.GetData()
        
        log.debug("AddDirEvent:Got data: %s", data)
            
        #Update observers
        if data == None:
            log.error("No matching DataDescription found!")
            return
        
        log.debug("AddDirEvent: Remaining entry: %s", data.name)
        self.venueState.data[data.id] = data
        
        for s in self.observers:
            log.debug("Observer to handle event: %s", s)
            s.AddDir(data)

    def RemoveDirEvent(self, event):
        log.debug("RemoveDirEvent:Entered RemoveDirEvent!")
        data = event.GetData()
        
        self.venueState.RemoveData(data)
        
        for s in self.observers:
            log.debug("Observer to handle event: %s", s)
            s.RemoveDir(data)


    def UpdateDataEvent(self, event):
        log.debug("UpdateDataEvent: Got Update Data Event")

        data = event.GetData()
                
        if data.type == "None" or data.type == None:
            # Venue data gets saved in venue state
            self.venueState.UpdateData(data)
                      
        for s in self.observers:
            s.UpdateData(data)

    def RemoveDataEvent(self, event):
        log.debug("RemoveDataEvent: Got Remove Data Event")
        data = event.GetData()
        
        log.debug("RemoveDataEvent: Data type is: %s", data.type)
	log.debug("RemoveDataEvent: Data is: %s", data)
        if data.type == "None" or data.type == None:
            # Venue data gets removed from venue state
            self.venueState.RemoveData(data)
            
        for s in self.observers:
            s.RemoveData(data)
                
    def AddServiceEvent(self, event):
        log.debug("AddServiceEvent: Got Add Service Event")

        service = event.GetData()
        self.venueState.AddService(service)
        for s in self.observers:
            s.AddService(service)

    def UpdateServiceEvent(self, event):
        log.debug("UpdateServiceEvent: Got Update Service Event")

        service = event.GetData()
        self.venueState.UpdateService(service)
        for s in self.observers:
            s.UpdateService(service)

    def RemoveServiceEvent(self, event):
        log.debug("RemoveServiceEvent: Got Remove Service Event")

        service = event.GetData()
        self.venueState.RemoveService(service)
        for s in self.observers:
            s.RemoveService(service)

    def AddApplicationEvent(self, event):
        log.debug("AddApplicationEvent: Got Add Application Event")

        app = event.GetData()
        self.venueState.AddApplication(app)
        for s in self.observers:
            s.AddApplication(app)

    def UpdateApplicationEvent(self, event):
        log.debug("UpdateApplicationEvent: Got Update Application Event")
        app = event.GetData()
        self.venueState.UpdateApplication(app)
        for s in self.observers:
            s.UpdateApplication(app)

    def RemoveApplicationEvent(self, event):
        log.debug("RemoveApplicationEvent: Got Remove Application Event")

        app = event.GetData()
        self.venueState.RemoveApplication(app)
        for s in self.observers:
            s.RemoveApplication(app)

    def AddConnectionEvent(self, event):
        log.debug("AddConnectionEvent: Got Add Connection Event")

        connection = event.GetData()
        self.venueState.AddConnection(connection)
        for s in self.observers:
            s.AddConnection(connection)

    def RemoveConnectionEvent(self, event):
        log.debug("RemoveConnectionEvent: Got Remove Connection Event")

        connection = event.GetData()
        self.venueState.RemoveConnection(connection)
        for s in self.observers:
            s.RemoveConnection(connection)

    def SetConnectionsEvent(self, event):
        log.debug("SetConnectionEvent: Got Set Connections Event")

        connectionList = event.GetData()
        #self.venueState.SetConnections(connectionList)
        for s in self.observers:
            s.SetConnections(connectionList)

    def AddStreamEvent(self, event):
        log.debug("AddStreamEvent: Got Add Stream Event")
        streamDesc = event.GetData()

        # Add the stream to the local stream store
        self.streamDescList.append(streamDesc)

        try:
            self.nodeService.AddStream(streamDesc)
        except:
            log.info("Error adding stream to node")
        
        for s in self.observers:
            s.AddStream(streamDesc)
    
    def ModifyStreamEvent(self, event):
        log.debug("ModifyStreamEvent: Got Modify Stream Event")
        streamDesc = event.GetData()

        # Modify the local stream store
        for i in range(len(self.streamDescList)):
            if self.streamDescList[i].id == streamDesc.id:
                self.streamDescList[i] = streamDesc

        # Update event subscribers (the UI)
        for s in self.observers:
            s.ModifyStream(streamDesc)
        
    
    def RemoveStreamEvent(self, event):
        log.debug("RemoveStreamEvent: Got Remove Stream Event")
        streamDesc = event.GetData()

        # Remove the stream from the local stream store
        for i in range(len(self.streamDescList)):
            if self.streamDescList[i].id == streamDesc.id:
                del self.streamDescList[i]

        try:
            self.nodeService.RemoveStream(streamDesc)
        except:
            log.info("Error removing stream from node")

        for s in self.observers:
            s.RemoveStream(streamDesc)

    def OpenAppEvent(self, event):
        appCmdDesc = event.GetData()
        log.debug("OpenAppEvent: Got Start App Event %s %s %s"
                  %(appCmdDesc.appDesc, appCmdDesc.command, appCmdDesc.verb))
       
        for s in self.observers:
            s.OpenApplication(appCmdDesc)
                   
    def AddTextEvent(self,name, text):
        log.debug("TextEvent: Got Text Event")
        
        for s in self.observers:
            s.AddText(name,text)
            
    def SOAPFaultHandler(self, proxy, ex):
        """
        Handle a fault raised by an invocation through the venue server
        proxy.

        @param proxy: SOAPpy proxy through which the invocation failed
        @param ex: The exception that was raised

        @return: a true value if the invocation should be retried.

        """
        log.debug("SOAP FAULT: %s %s", proxy, ex)
        
        log.exception("SOAP fault occurred")

        return 0
        
            
    # end Event Handlers
    #
    ##########################################################################

    ##########################################################################
    #
    # Basic Implementation
        
    def AddObserver(self, observer):
        if not observer:
            raise ValueError, "Attempt to add null Observer"

        if not isinstance(observer,VenueClientObserver):
            raise ValueError, "Attempt to add non-Observer"
        
        self.observers.append(observer)

    def RemoveObserver(self, observer):
        if not observer:
            raise ValueError, "Attempt to remove null Observer"

        try:
            self.observers.remove(observer)
        except Exception, e:
            # Ignore exception related to non existent observer. Log in
            # case its something else
            log.debug("Failed to remove observer: " + e)
        
    #Added by NA2-HPCE
    def SetVCUI(self, vcui):
        self.__venueClientUI = vcui
	
    def GetVenueProxy(self):
        return self.__venueProxy
        
    #
    # Enter/Exit
    #
    
    def __EnterVenue(self,URL,withcert=0):
        #
        # Enter the venue
        #
        self.venueUri = str(URL)
        self.certRequired = withcert
        if withcert:
            ctx = self.app.GetContext()
            transdict = {'ssl_context':ctx}
            log.info("Using certificate with VenueIW")
            self.__venueProxy = VenueIW(URL,transdict=transdict) #, tracefile=sys.stdout)
            self.__secondaryVenueProxy = VenueIW(URL,transdict=transdict) #, tracefile=sys.stdout)
        else:
            self.__venueProxy = VenueIW(URL) #, tracefile=sys.stdout)
            self.__secondaryVenueProxy = VenueIW(URL) #, tracefile=sys.stdout)

        if not self.__venueClientUI == None:
            self.__venueClientUI.SetVenueProxy(self.__venueProxy)

        log.debug("EnterVenue: Invoke Venue.Enter")
        self.profile.connectionId = self.__venueProxy.Enter( self.profile )
        log.debug('after Venue.Enter')
    
        log.debug("EnterVenue: Invoke Venue.getstate")
        state = self.__venueProxy.GetState()
        log.debug("EnterVenue: done Venue.getstate")

        evtLocation = state.eventLocation.split(":")
        if len(evtLocation) > 1:
            evtLocation = (str(evtLocation[0]), int(evtLocation[1]))

        # Are we changing textLocation?
        if self.textLocation:
            prevTextLocation = self.textLocation
        else:
            prevTextLocation = None

        self.textLocation = state.textLocation.split(":")
    
        if len(self.textLocation) > 1:
            self.textLocation = (str(self.textLocation[0]), int(self.textLocation[1]))
        if prevTextLocation and not self.textLocation[0].startswith(prevTextLocation[0]):
            try:
                self.jabber.Logout()
            except:
                log.exception("Moving textLocation: jabber.Logout failed")

        self.dataStoreUploadUrl = state.dataLocation
                        
        # next line needed until zsi can handle dictionaries.
        self.venueState = VenueState(uniqueId=state.uniqueId, name=state.name, description=state.description, uri=state.uri, connections=state.connections, clients=state.clients, data=state.data, eventLocation=evtLocation, textLocation=state.textLocation, dataLocation = state.dataLocation, applications=state.applications, services=state.services)
        
        # Retreive stream descriptions
        self.streamDescList = []
        if len(self.capabilities) > 0:
            self.streamDescList = self.__venueProxy.NegotiateCapabilities(self.profile.connectionId,
                                                                          self.capabilities) 
        self.venueUri = URL

        log.debug("Setting isInVenue flag.")
    
        # Handle the remaining Enter-related tasks in a separate thread
        threading.Thread(target=self.DoPostEnter,args=[evtLocation],
                         name='VenueClient.DoPostEnter').start()

        # Finally, set the flag that we are in a venue
        self.isInVenue = 1


    def DoPostEnter(self,evtLocation):
        # Create event client
        coherenceCallbacks = {
            Event.ENTER: self.AddUserEvent,
            Event.EXIT: self.RemoveUserEvent,
            Event.MODIFY_USER: self.ModifyUserEvent,
            Event.ADD_DATA: self.AddDataEvent,
            Event.ADD_DIR: self.AddDirEvent,
            Event.UPDATE_DATA: self.UpdateDataEvent,
            Event.REMOVE_DATA: self.RemoveDataEvent,
            Event.REMOVE_DIR: self.RemoveDirEvent,
            Event.ADD_SERVICE: self.AddServiceEvent,
            Event.UPDATE_SERVICE: self.UpdateServiceEvent,
            Event.REMOVE_SERVICE: self.RemoveServiceEvent,
            Event.ADD_APPLICATION: self.AddApplicationEvent,
            Event.UPDATE_APPLICATION: self.UpdateApplicationEvent,
            Event.REMOVE_APPLICATION: self.RemoveApplicationEvent,
            Event.ADD_CONNECTION: self.AddConnectionEvent,
            Event.REMOVE_CONNECTION: self.RemoveConnectionEvent,
            Event.SET_CONNECTIONS: self.SetConnectionsEvent,
            Event.ADD_STREAM: self.AddStreamEvent,
            Event.MODIFY_STREAM: self.ModifyStreamEvent,
            Event.REMOVE_STREAM: self.RemoveStreamEvent,
            Event.OPEN_APP: self.OpenAppEvent
            }

        ssl_ctx = None
        if self.certRequired:
            log.info("Using certificate with event client")
            ssl_ctx = self.app.GetContext()
        self.eventClient = VenueEventClient(evtLocation, 
                                       self.profile.connectionId,
                                       self.venueState.GetUniqueId(),
                                       ssl_ctx=ssl_ctx)
                                       
        for e in coherenceCallbacks.keys():
            self.eventClient.RegisterEventCallback(e, coherenceCallbacks[e])
        self.eventClient.Start()
        
        # Start sending heartbeats
        self.Heartbeat()

        # Create text client
        try:    
            if self.textLocation:
                self.__StartJabber(self.textLocation)
        except Exception,e:
            log.exception("EnterVenue.__StartJabber failed")
            self.warningString += "\nJabber Client failed to initialize"

        # 
        # Update the node service with stream descriptions
        #

        try:

            # Update node with those streams
            self.UpdateNodeService()
        except NetworkLocationNotFound, e:
            log.debug("UpdateNodeService: Couldn't update stream with transport/provider info")
            if self.transport == 'unicast':
                self.warningString += '\nConnection to unicast bridge %s failed. Select other bridge.'%(self.currentBridge.name)
            else:
                self.warningString += '\nError connecting media tools.'
        except Exception, e:
            # This is a non fatal error, users should be notified
            # but still enter the venue
            log.exception("EnterVenue: Error updating node service")

        # Cache profiles from venue.
        try:
            log.debug("Updating client profile cache.")
            clients = self.venueState.clients
            for client in clients.values():
                self.UpdateProfileCache(client)
        except Exception, e:
            log.exception("Unable to update client profile cache.")
        
        if self.warningString:
            uw = UserWarning(self.warningString)
            for s in self.observers:
                try:
                    s.HandleError(uw)
                except:
                    log.exception("Observer failed while handling error; class=%s, warning=%s", s.__class__, self.warningString)


    def StopBeacon(self):
        ''' Stop the beacon client'''
        if self.beacon:
            try:
                self.beacon.Stop()
            except:
                log.exception("VenueClient.StopBeacon failed")
                
    def StartBeacon(self):
        ''' Create and start the beacon client listening to beaconLocation '''

        try:
            # Get beacon location
	    for s in self.streamDescList:
                for cap in s.capability:
                    if cap.type == "Beacon":
		        self.beaconLocation = s.location
                        for netloc in s.networkLocations:
                            if self.transport == netloc.GetType():
                                self.beaconLocation = netloc

            # Create beacon
            if self.beaconLocation:
		if self.beacon == None:
		    self.beacon = Beacon()
                elif(self.beacon.GetConfigData('groupAddress') != self.beaconLocation.host or
                     self.beacon.GetConfigData('groupPort') != self.beaconLocation.port):
		    # Beacon reconfig; stop running beacon
                    log.info("Beacon being reconfigured, stopping running beacon")
                    self.beacon.Stop()

                self.beacon.SetConfigData('user', self.profile.name)
                self.beacon.SetConfigData('groupAddress',
                                          str(self.beaconLocation.host))
                self.beacon.SetConfigData('groupPort',
                                          str(self.beaconLocation.port))
                log.info("VenueClient.StartBeacon: Address %s/%s"
                         %(self.beaconLocation.host, self.beaconLocation.port))
                self.beacon.Start()
            else:
		log.info('No beacon location, not starting beacon client')
                              
        except:
	    log.exception("VenueClient.StartBeacon failed")
                   
    def __StartJabber(self, textLocation, restart=False):
        jabberHost = textLocation[0]
        jabberPort = textLocation[1]
        
        self.jabberNameRetries = 0
        
        if self.jabberHost != jabberHost:
            # Create jabber chat client if necessary
            self.jabber.Connect(jabberHost, jabberPort) 
        

            jabberId = str(self.profile.connectionId)
            jabberPwd = str(self.profile.connectionId)
            
            # Set the user information
            # In the case of a restart, we have to generate a different
            # jabberId in order to Register() successfully.
            if restart:
                self.jabberIdRetries += 1
                idRetries = self.jabberIdRetries
                while idRetries > 0:
                    jabberId = jabberId + "_"
                    idRetries -= 1
            self.jabber.SetUserInfo(self.profile.name,
                                    jabberId, jabberPwd, 'AccessGrid'+str(self.profile.connectionId))
            
            try:
                self.jabber.Login()
                log.info("Successfully logged in to Jabber")
            except AuthorizationFailure:
                try:
                    ## Register the user in the jabber server
                    log.info("Login failure; registering account %s", jabberId)
                    self.jabber.Register()
                    log.info("Logging in to Jabber")
                    self.jabber.Login()
                    log.info("Successfully logged in to Jabber")
                except:
                    log.exception("Error registering jabber acount %s", jabberId)
                    raise

            self.jabberHost = jabberHost
               
        # Create room
        server = str(self.venueState.uri).split('/')[2].split(":")[0]
        currentRoom = self.venueState.name.replace(" ", "-")
        currentRoom = currentRoom+"("+server+")"
        
        # Create conference host
        conferenceHost = "conference"
        domain = jabberHost.split('.')[1:]
       
        for i in range(len(domain)):
            conferenceHost = conferenceHost + '.' + domain[i]

        self.chatLocation = "%s@%s" % (currentRoom,conferenceHost)
        self.jabber.SetChatRoom(currentRoom, conferenceHost)
        self.jabber.SendPresence('available')

    def __RestartJabber(self):
        """
        Following an unexpected jabber disconnection, establish a new one.

        On normal disconnection e.g. changing venues, we would execute:
            self.jabber.SendPresence('unavailable')
            self.jabber.ClearChatRoom()
            self.jabber.Logout()
        but these generate exceptions in this (unexpected disconnect) case,
        so we just go ahead and create an entirely new connection.
        """

        # Try to tell the user we have a problem
        self.jabber.jabberPanel.OutputText("Internal Notification: ",
                              "Trying to reconnect to text server")
        textPanel = self.jabber.jabberPanel

        self.jabber = JabberClient()
        self.jabber.SetPanel(textPanel)
        self.jabber.SetPresenceCB(self.JabberPresenceCB)
        self.maxJabberNameRetries = 3
        self.jabberNameRetries = 0
        self.jabberHost = None

        try:
            if self.textLocation:
                self.__StartJabber(self.textLocation, True)
            else:
                log.debug("Can't __RestartJabber - no textLocation")
        except Exception, e:
            log.exception("__RestartJabber - __StartJabber failed: %s" % e)

    def EnterVenue(self, URL,withcert=0):
        """
        EnterVenue puts this client into the specified venue.

        URL : url to the venue
        """
        URL = str(URL)
        URL = BuildServiceUrl(URL,'https',8000,'Venues/default')
        log.debug("EnterVenue; url=%s type=%s", URL,type(URL))
        
        # Initialize a string of warnings that can be displayed to the user.
        self.warningString = ''
        enterSuccess = 1
        errorInNode = 0

        try:
            if self.nodeService:
                self.capabilities = self.nodeService.GetCapabilities()
                self.capabilities += self.beaconCapabilities 
            for cap in self.capabilities:
		log.debug("Capability on VenueEnter: %s", cap)
            
        except:
            log.exception("EnterVenue: Exception getting capabilities")
            errorInNode = 1
            
        if not self.capabilities:
            self.capabilities = []
            self.capabilities += self.beaconCapabilities 
           
        # Set media and beacon indicators in client profile based on capabilities
        self.profile.video = self.profile.audio = self.profile.display = self.profile.beacon = 0
        for c in self.capabilities:
            if c.type == 'video':
                if c.role == 'producer':
                    self.profile.video = 1
                if c.role == 'consumer':
                    self.profile.display = 1
            if c.type == 'audio':
                self.profile.audio = 1
            if c.type == 'Beacon' and int(self.preferences.GetPreference(Preferences.BEACON)):
                self.profile.beacon = 1

        try:
            # Enter the venue
            log.debug('calling __EnterVenue')
            self.__EnterVenue(URL,withcert)
            log.debug('after __EnterVenue')

            # Return a string of warnings that can be displayed to the user
            if errorInNode:
                self.warningSting = self.warningString + '\n\nA connection to your node could not be established, which means your media tools might not start properly.  If this is a problem, try changing your node configuration by selecting "Preferences->Manage My Node..." from the main menu'
        except (socket.error,socket.gaierror), e:
            log.exception('Socket exception entering venue')
            self.warningString += '\n' + e.args[1]
            enterSuccess = 0
        except HostingException,e:
            enterSuccess = 0
            log.exception("Hosting exception entering venue")
            try:
                mod,klass = GetHostingExceptionModuleAndClassName(e)
            except Exception:
                klass = 0
            if klass == "CertificateRequired":
                raise CertificateRequired
                self.warningString += "A certificate is required for entry into this Venue,\nand this version of the software does not support\nthe use of certificates with the Venue Client.\nUpgrade to the next version of the Access Grid\nsoftware before trying to enter this Venue."
            else:
                log.exception('"EnterVenue: failed with hosting exception')
                #self.warningString += 'exception: %s:%s' % (str(mod),str(klass))
        except Exception, e:
            log.exception("EnterVenue: failed")
            enterSuccess = 0
            self.warningString = str(e)

        for s in self.observers:
            try:
                # enterSuccess is true if we entered.
                s.EnterVenue(URL, self.warningString, enterSuccess)
            except:
                log.exception("Exception in observer")

        return self.warningString

    def __ExitVenue(self):

        # Cancel the heartbeat
        if self.heartBeatTimer is not None:
            log.debug('ExitVenue: cancelling heartbeat timer')
            self.heartBeatTimer.cancel()

        self.exitingLock.acquire()
        if self.exiting:
            log.debug("ExitVenue: already exiting, returning.")
            self.exitingLock.release()
            return
        self.exiting = 1
        self.exitingLock.release()

        try:
            self.__venueProxy.Exit( self.profile.connectionId )
            
        except Exception:
            log.exception("ExitVenue: ExitVenue exception")

        try:
            if self.eventClient:
                log.debug("ExitVenue: Stop event client obj")
                self.eventClient.Stop()
                log.debug("ExitVenue: Remove event client reference")
                self.eventClient = None
        except:
            log.exception("ExitVenue: Can not stop event client")
            
        log.info("ExitVenue: Stopping text client")

        try:
            self.jabber.SendPresence('unavailable')
            self.jabber.ClearChatRoom()
        except:
            log.exception("ExitVenue: Exit jabber failed")

        try:
            self.StopBeacon()
        except:
            log.exception("ExitVenue: Exit beacon failed")
        self.__InitVenueData()
        self.isInVenue = 0
        self.exitingLock.acquire()
        self.exiting = 0
        self.exitingLock.release()
        
    def ExitVenue( self,updateNode=1 ):
        """
        ExitVenue removes this client from the specified venue.
        """
        log.info("ExitVenue")

        # Tell UI and others that we are exiting.
        for s in self.observers:
            s.ExitVenue()

        # Exit the venue
        # This causes the venue server to do the following:
        # Remove producers for this client.
        # Remove personal data (causes remove data events?)
        # Distribute an EXIT event.
        # Remove client from venue list of clients.
        #
        # The distribution of the EXIT event may arrive back at the
        # client if the event client has not been stopped first.
        #
        # Unfortunately there's a bit of a race here, as stopping
        # the event client causes the server to see an EOF,
        # which it interprets as a client disconnection, which will
        # in turn trigger the RemoveUser logic above.
        #
        # Ah, a likely solution is to stop the event client with a
        # special "I'm disconnecting and it's okay" event that
        # doesn't trigger the RemoveUser logic.
        # 

        # Stop the event client
        # NOT USED, so comment out for now
        #log.info("ExitVenue: Stopping event client")
        #try:
          #
          #if self.eventClient:
            #log.debug("ExitVenue: Send client exiting event")
            #self.eventClient.Send(ClientExitingEvent(self.venueState.uniqueId,
                                                     #self.privateId))
        #except:
            #log.exception("ExitVenue: Can not send client exiting event to event client")
        
        # Stop the node services
        if updateNode:
            try:
                log.info("ExitVenue: Stopping node services")
                self.nodeService.StopServices()

            except Exception:
                log.info("ExitVenue: Error stopping node services")
            
        self.__ExitVenue()

         
    #
    # NodeService-related calls
    #

    def UpdateNodeService(self):
        """
        Send venue streams to the node service
        """
        log.debug("UpdateNodeService: Method UpdateNodeService called")
        exc = None

        # Ensure that streams are using the intended addresses (multicast or a particular bridge)
        self.UpdateStreams()

        # Send streams to the node service
        try:
            log.debug("Setting node service streams")
            if self.nodeService:
                self.nodeService.SetStreams( self.streamDescList )
        except:
            log.exception("Error setting streams")
            
        # Raise exception if occurred
        if exc:
            raise exc

    def UpdateServiceClientProfile(self,profile):
        if self.nodeService:
            services = self.nodeService.GetServices()
            for service in services:
                try:
                    AGServiceIW(service.uri).SetIdentity(self.profile)
                except:
                    log.exception('failed to update %s with profile', service.name)
            
    def UpdateStreams(self):
        for stream in self.streamDescList:
            self.UpdateStream(stream)

        # Restart the beacon so the new transport is used
        log.debug('Checking preference and starting beacon')
        if int(self.preferences.GetPreference(Preferences.BEACON)):
            if self.beacon:
                # stop the beacon
                log.debug('Stopping beacon')
                self.StopBeacon()
                
            # start the beacon
            log.debug('Starting beacon')
            self.StartBeacon()
        else:
            log.debug('NOT starting beacon, user preference turned off')


    def UpdateStream(self,stream):
        """
        Apply selections of transport and netloc provider to the given stream.
        """
        found = 0

        log.info("In UpdateStream: transport=%s", self.transport)
               
        # Check streams if they have a network location
        for netloc in stream.networkLocations:
            # If transport is multicast, use the location
            if self.transport == "multicast" and netloc.GetType() == self.transport:
                stream.location = netloc
                found = 1
            # If UMTP, use the multicast location
            #elif self.transport == "unicast" and self.currentBridge.serverType == UMTP_TYPE and netloc.GetType() == "multicast":
            #    stream.location = netloc
            #    found = 1
                                    
        if not found:# and self.transport == "unicast":# and self.currentBridge.serverType == QUICKBRIDGE_TYPE:


            if not self.currentBridge or self.currentBridge.status != STATUS_ENABLED:
                if self.currentBridge:
                    log.info("Current bridge %s is disabled by user, searching for other bridge", self.currentBridge.name)
                self.currentBridge = self.FindBridge(self.bridges.values())
                if not self.currentBridge:
                    raise NetworkLocationNotFound("transport=%s"%(self.transport,))
                log.info("Using new bridge %s", self.currentBridge.name)

            if self.currentBridge.serverType == QUICKBRIDGE_TYPE:
                qbc = QuickBridgeClient.QuickBridgeClient(self.currentBridge.host, self.currentBridge.port)
            elif self.currentBridge.serverType == UMTP_TYPE:
                qbc = UMTPClient.UMTPClient(self.currentBridge.host,self.currentBridge.port)

            try:
                stream.location = qbc.JoinBridge(stream.networkLocations[0])
                log.debug("Got location from bridge: %s", stream.location)
                if self.currentBridge.serverType != UMTP_TYPE:        # HACK!
                    stream.networkLocations.append(stream.location)
              
            except QuickBridgeClient.ConnectionError,e:
                self.currentBridge.rank = BridgeDescription.UNREACHABLE
            except Exception,e:
                log.exception("VenueClient.UpdateStream: Failed to connect to bridge %s"%(self.currentBridge.name))
                raise NetworkLocationNotFound("transport=%s; provider=%s %s" % 
                                              (self.transport, self.currentBridge.name, self.currentBridge.host))
    def SendEvent(self,eventType, data):
        self.eventClient.Send(eventType, data)

    def Shutdown(self):

        self.__StopWebService()
        
        if self.server:
            try:
                self.server.Stop()
            except:
                log.exception("Failed to stop server")

        if self.eventClient:
            self.eventClient.Stop()
            
        if self.beacon:
            self.beacon.Stop()

        log.info('Shutting down jabber client')
        if self.jabber:
            self.jabber.Logout()
            
        if self.bridgePinger:
            log.info('Shutting down bridge ping thread')
            self.bridgePinger.close()
       
    def UpdateProfileCache(self, profile):
        try:
            self.cache.updateProfile(profile)
        except InvalidProfileException:
            log.exception("UpdateProfileCache: InvalidProfile when storing a venue user's profile in the cache.")
	    
	    
    """
    This method returns the node configurations
    """
    def GetNodeConfigurations(self):
        nodeConfigurations = []
        if self.nodeService:
            try:
                nodeConfigurations = self.nodeService.GetConfigurations()
            except:
                log.exception('Exception retrieving node configurations')
        return nodeConfigurations
    
    def LoadNodeConfiguration(self, configuration):
	return self.nodeService.LoadConfiguration( configuration )
            
    #
    # Venue calls
    #

    def GetVenues(self):
        if not self.IsInVenue():
            return []
        
        self.preferences = self.app.GetPreferences()

        # Use preference for navigation layout 
        displayMode = self.preferences.GetPreference(Preferences.DISPLAY_MODE)
       
        if displayMode == Preferences.EXITS:
            return self.__venueProxy.GetConnections()
           
        elif displayMode == Preferences.MY_VENUES:
            return ["my venues"]
        elif displayMode == Preferences.EXITS:
            return ["exits"]

    def GetVenueConnections(self, venueUrl):
        venues =  self.__venueProxy.GetConnections()
        return venues

    def UpdateClientProfile(self,profile):
        log.debug('VenueClient.UpdateClientProfile')
        try:
            self.UpdateServiceClientProfile(profile)
        except:
            log.exception("Error occurred updating profile used by services")
        if self.GetVenue() != None:
            log.debug("Update client profile in venue")

            try:
                self.__venueProxy.UpdateClientProfile(profile)
            except:
                log.exception("Error occured when trying to update profile")
        else:
            log.debug("Can not update client profile in venue - not connected")
        
    def CreateApplication(self, appName, appDescription, appMimeType):
        self.__venueProxy.CreateApplication(appName,appDescription,appMimeType)

    def DestroyApplication(self,appId):
        self.__venueProxy.DestroyApplication(appId)
        
    def UpdateApplication(self,appDescription):
        self.__venueProxy.UpdateApplication(appDescription)
        
    def AddService(self,serviceDescription):
        #try:
        self.__venueProxy.AddService(serviceDescription)
        #except Exception,e:
        #    if e.faultstring == "ServiceAlreadyPresent":
        #        raise ServiceAlreadyPresent
        #    raise

    def UpdateService(self,serviceDescription):
        self.__venueProxy.UpdateService(serviceDescription)
            
    def RemoveService(self,serviceDescription):
        self.__venueProxy.RemoveService(serviceDescription)
        
    def RemoveData(self, data):
        """
        This method removes a data from the venue. If the data is personal, this method
        also removes the data from the personal data storage.
        
        **Arguments:**
        
        *data* The DataDescription we want to remove from vnue
        """
        log.debug("Remove data: %s from venue" %data.name)

        dataList = []
        dataList.append(data)
    
        if data.type == None or data.type == 'None':
            # Venue data
            self.__venueProxy.RemoveData(data)
            
            
        else:
            # Ignore this until we have authorization in place.
            raise NotAuthorizedError
        
    #Added NA2-HPCE
    def RemoveDir(self, data):
        """
        This method removes a directory from the venue. If the data is personal, this method
        also removes the data from the personal data storage.
        
        **Arguments:**
        
        *data* The DataDescription we want to remove from vnue
        """
        log.debug("Remove data: %s from venue" %data.name)

        dataList = []
        dataList.append(data)
    
        if data.type == None or data.type == 'None':
            # Venue data
            self.__venueProxy.RemoveDir(data)           
        else:
            # Ignore this until we have authorization in place.
            raise NotAuthorizedError

    def UpdateData(self, data):
        log.debug("Update data: %s from venue" %data.name)
        
        if data.type == None or data.type == 'None':
            # Venue data
            try:
                self.__venueProxy.UpdateData(data)
            except:
                log.exception("Error updating data")
                raise
            
        else:
            # Ignore this until we have authorization in place.
            raise NotAuthorizedError
        
    def JabberPresenceCB(self,jabbername,presenceType,presenceStanza):

        if (presenceType == 'error' and presenceStanza.error_e.code_ == "409"
            and self.jabberNameRetries <= self.maxJabberNameRetries):
            self.jabberNameRetries += 1
            self.jabber.name = self.jabber.name + " "
            self.jabber.to = self.jabber.to + " "
            self.jabber.SendPresence('available')
            return
        
        try:
            index = jabbername.index('/')
            username = jabbername[index+1:]
        except ValueError:
            username = jabbername
        except:
            log.exception('Exception extracting name from jabber username')
            username = jabbername
        profile = ClientProfile()
        profile.name = username
        profile.profileType = 'jabber'
        profile.connectionId = jabbername
        profile.email = ''
        profile.location = ''
        profile.phoneNumber = ''
        profile.homeVenue = ''
        if presenceType == 'available':
            for s in self.observers:
                s.AddUser(profile)
        elif presenceType == 'unavailable':
            for s in self.observers:
                s.RemoveUser(profile)
        else:
            log.info('Presence of unexpected type %s for name %s', presenceType, jabbername)
            
                
    def GetEncryptMedia(self):
        return self.__venueProxy.GetEncryptMedia()
        
                                        
    # end Basic Implementation
    #
    ########################################################################

    ########################################################################
    #
    # Accessors
    

    #
    # Venue State
    #
    
    def GetVenueState(self):
        return self.venueState

    def GetVenueStreams(self):
        return self.streamDescList
        
    def GetEventChannelId(self):
        return self.venueState.GetUniqueId()

    def GetVenueData(self):
        return self.venueState.GetData()

    def GetVenue( self ):
        """
        GetVenue gets the venue the client is currently in.
        """
        return self.venueUri

    def GetVenueServer(self):
        """
        Get venue server gets the server the client
        is currently connected to.
        """
        serverUri = None
        
        if self.venueUri:
            proto = self.venueUri.split(':')[0]
            hostPort = self.venueUri.split('/')[2]
            serverUri = "%s://%s/VenueServer" % (proto,hostPort)

        return serverUri
        
    def GetVenueName(self):
        return self.venueState.GetName()

    def GetVenueDescription(self):
        return self.venueState.GetDescription()
    
    def GetDataStoreUploadUrl(self):
        return self.dataStoreUploadUrl
        
    def GetBeaconSources(self):
        """
        Returns a list of beacon hosts.
        Each list item is {hostname,IPaddress,SSRC}.
        """
        
        if not self.beacon:
            return []
            
        beaconHosts = []
        sources = self.beacon.GetSources()
        for s in sources:
            cname = self.beacon.GetSdesData(s,1)
            beaconHosts.append(BeaconSource(cname,s))
            
        return beaconHosts
        
    def GetBeaconSourceData(self,ssrc):
        """
        Returns a list of items, each of which is [ssrc,networkStatus]
        
        where networkStatus is also a list, with items:

             [Central Loss, Local Loss, Fract Loss, Central RTT, 
             Local RTT, Central Jitter, Local Jitter ]
              
        """
        ret = []
        
        sources = self.beacon.GetSources()
        
        # Bail out of the given source is not among known sources
        if ssrc not in sources:
            return []
        
        # Build up return list
        for s in sources:
            rr = self.beacon.GetReport(ssrc,s)
            if rr:
                item = BeaconSourceData(s,rr.total_lost,rr.fract_lost,rr.jitter)
            else:
                item = BeaconSourceData(s,-1,-1,-1)
            ret.append(item)
            
        return ret


    #
    # Personal Data
    #

        
    def GetUsers(self):
        return self.venueState.GetUsers()
        
    def GetServices(self):
        return self.venueState.GetServices()
        
    def GetApplications(self):
        return self.venueState.GetApplications()
                
    def GetConnections(self):
        return self.venueState.GetConnections()
        
    def GetVenueURL(self):
        return self.venueState.GetUri()
        
    def GetNodeServiceURL(self):
        return self.nodeServiceUri
        
    def GetStreams(self):
        return self.streamDescList
        
    def GetChatLocation(self):
        return self.chatLocation
        
    def GetClientProfile(self):
        return self.preferences.GetProfile()

    #
    # NodeService Info
    #
        
    def SetNodeUrl(self, url):
        """
        This method sets the node service url

        **Arguments:**
        
        *url* The string including the new node url address
        """
        # Check if this is local host, then avoid using the
        # soap interface
        
        log.debug("SetNodeUrl: Set node service url:  %s" %url)
        self.nodeServiceUri = url
        self.nodeService = AGNodeServiceIW(url)
        
        # assume that when the node service uri changes, the node service
        # needs identity info
        self.isIdentitySet = 0

    def GetNodeService(self):
        return self.nodeService
        
    def GetNodeServiceUri(self):
        return self.nodeServiceUri

    def SetVideoDisplayEnabled(self,enableFlag):
        try:
            found = 0
            
            if self.nodeService:
                serviceList = self.nodeService.GetServices()
                for service in serviceList:
                    for cap in service.capabilities:
                        if cap.type == 'video' and cap.role == 'consumer':
                            service.GetObject().SetEnabled(enableFlag)
                            found = 1

            if not found:
                raise NoServices
            
        except NoServices:
            raise
        except:
            log.info("Error enabling video")
            
        
    def SetVideoEnabled(self,enableFlag):
        try:
            found = 0
            
            if self.nodeService:
                serviceList = self.nodeService.GetServices()
                for service in serviceList:
                    for cap in service.capabilities:
                        if cap.type == 'video' and cap.role == 'producer':
                            service.GetObject().SetEnabled(enableFlag)
                            found = 1

            if not found:
                raise NoServices

        except NoServices:
            raise
        except:
            log.exception("Error enabling video")
            
    def SetAudioEnabled(self,enableFlag):
        try:
            if self.nodeService:
                self.nodeService.SetServiceEnabledByMediaType("audio",enableFlag)
        except:
            log.exception("VenueClient.SetAudioEnabled: Error enabling audio")
            
    #
    # User Info
    #

    def SaveProfile(self):
        self.preferences.SetProfile(self.profile)
        self.jabberNameRetries = 0
        self.jabber.SendNameChange(self.profile.name)
        if self.beacon:
            self.beacon.SetName(str(self.profile.name))
        self.preferences.StorePreferences()
    
    def SavePreferences(self):
        self.preferences.StorePreferences()
        self.SetBridges(self.preferences.GetBridges())
        
    def GetPreferences(self):
        return self.preferences
    #
    # Bridging Info
    #
    
    def GetBridges(self):
        ''' Get a list of available unicast bridges'''
        return self.bridges

    def SetBridges(self, bridges):
        self.bridges = bridges

    def GetCurrentBridge(self):
        ''' Get selected unicast bridge'''
        return self.currentBridge

    def SetCurrentBridge(self, bridgeDescription):
        ''' Select bridge to use for unicast connections '''
        self.currentBridge = bridgeDescription
        
    def SetTransport(self,transport):
        ''' Set transport used, either multicast or unicast '''
        self.transport = transport

    def GetTransport(self):
        ''' Get transport used, either multicast or unicast '''
        return self.transport

    #
    # Other
    #
    
    def IsInVenue(self):
        return self.isInVenue
        
    def IsVenueAdministrator(self):
        # Determine if we are an administrator so we can add
        # administrator features to UI.
        
        isVenueAdministrator = 0
        try:
            authUrl = self.venueUri + '/Authorization'

            authClient = AuthorizationManagerIW(authUrl)
            roles = authClient.GetRolesForSubject(Application.instance().GetDefaultSubject())

            for r in roles:            
                if r.name == "Administrators":
                    isVenueAdministrator = 1

        except Exception:
        
            log.exception("Error retrieving admin list")
                
        return isVenueAdministrator
        
        
    def GetMulticastStatus(self):
        if self.multicastWatcher:
            return self.multicastWatcher.GetStatus()
        return 0

    def GetBeacon(self):
        return self.beacon

    def GetConnectionId(self):
        return self.profile.connectionId
        
    def GetVersion(self):
        return Version.GetVersion()
    
    def SetMulticastWatcherHostPort(self,host,port):
        if self.multicastWatcher:
            self.multicastWatcher.SetHostPort(host,port)
    
    def IsValid(self):
        return 1

# Retrieve a list of urls of (presumably) running venue clients
def GetVenueClientUrls():
    urlList = dict()
    tdir = UserConfig.instance().GetTempDir()
    fileList = os.listdir(tdir)
    for filepath in fileList:
        if filepath.startswith("venueClientUrl"):
            fn = os.path.join(tdir, filepath)
            ctime = os.path.getctime(fn)
            f = open(fn,"r")
            venueClientUrl = f.read()
            f.close()

            urlList[ctime] = venueClientUrl         

    # This optimization makes the search for the venue client start with
    # the latest url first.
    keys = urlList.keys()
    keys.sort()
    
    nlist = map(urlList.get, keys)

    nlist.reverse()

    return nlist[0:4]


def GetVenueClientIW():
    venueClientUrlList = GetVenueClientUrls()
    for venueClientUrl in venueClientUrlList:
        try:
            venueClient = VenueClientIW(venueClientUrl)
            venueClient.IsValid()
            return venueClient
        except:
            pass
    return None

