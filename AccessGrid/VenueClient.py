#-----------------------------------------------------------------------------
# Name:        VenueClient.py
# Purpose:     This is the client side object of the Virtual Venues Services.
#
# Author:      Ivan R. Judson, Thomas D. Uram
#
# Created:     2002/12/12
# RCS-ID:      $Id: VenueClient.py,v 1.12 2003-02-03 14:18:05 judson Exp $
# Copyright:   (c) 2002
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------

import sys
from AccessGrid.hosting.pyGlobus.ServiceBase import ServiceBase
from AccessGrid.hosting.pyGlobus import Client
from AccessGrid.EventClient import EventClient
from AccessGrid.ClientProfile import ClientProfile
from AccessGrid.Types import *
from AccessGrid.Events import Event, HeartbeatEvent
from AccessGrid.scheduler import Scheduler

class VenueClient( ServiceBase ):
    """
    This is the client side object that maintains a stateful
    relationship with a Virtual Venue. This object provides the
    programmatic interface to the Access Grid for a Venues User
    Interface.  The VenueClient can only be in one venue at a
    time.
    """
    def __init__(self, profile=None):
        """
        This client class is used on shared and personal nodes.
        """
        self.profile = profile
        self.nodeServiceUri = None
        self.workspaceDock = None
        self.homeVenue = None
        self.followerProfiles = dict()
        self.__InitVenueData__()
        self.houseKeeper = Scheduler()
        
    def __InitVenueData__( self ):
        self.eventClient = None
        self.venueState = None
        self.venueUri = None
        self.venueProxy = None
        self.privateId = None
        self.streamDescList = []

    def Heartbeat(self):
        if self.eventClient != None:
            print "Sending heartbeat!"
            self.eventClient.Send(HeartbeatEvent(self.privateId))
            
    def SetProfile(self, profile):
        self.profile = profile
        
    def DoNothing(self, data):
        pass

    def RegisterCallbacks(self, client):
        coherenceCallbacks = {
           Event.ENTER: self.venueState.AddUser ,
           Event.EXIT: self.venueState.RemoveUser ,
           Event.MODIFY_USER: self.venueState.ModifyUser,
           Event.ADD_DATA: self.venueState.AddData ,
           Event.REMOVE_DATA: self.venueState.RemoveData ,
           Event.ADD_SERVICE: self.venueState.AddService ,
           Event.REMOVE_SERVICE: self.venueState.RemoveService ,
           Event.ADD_CONNECTION: self.venueState.AddConnection ,
           Event.REMOVE_CONNECTION: self.venueState.RemoveConnection,
           }

        for e in coherenceCallbacks.keys():
            client.RegisterCallback(e, coherenceCallbacks[e])

    def EnterVenue(self, URL):
        """
        EnterVenue puts this client into the specified venue.
        """

        try:

            if self.venueUri != None:
                self.ExitVenue()

            #
            # Retrieve list of node capabilities
            #
            if self.nodeServiceUri != None:
                self.profile.capabilities = Client.Handle( self.nodeServiceUri ).get_proxy().GetCapabilities()

            #
            # Enter the venue
            #
            (venueState, self.privateId, self.streamDescList ) = Client.Handle( URL ).get_proxy().Enter( self.profile )
            self.venueState = VenueState( venueState.description, venueState.connections, 
                                          venueState.users, venueState.nodes, 
                                          venueState.data, venueState.services, 
                                          venueState.eventLocation )
            self.venueUri = URL
            self.venueProxy = Client.Handle( self.venueUri ).get_proxy()

            #
            # Create the event client
            #
            self.eventClient = EventClient(self.venueState.eventLocation)
            self.RegisterCallbacks(self.eventClient)
            self.eventClient.start()
            
            self.heartbeatTask = self.houseKeeper.AddTask(self.Heartbeat, 15)
            self.heartbeatTask.start()
 
            # 
            # Update the node service with stream descriptions
            #
            if self.nodeServiceUri != None:
                Client.Handle( self.nodeServiceUri ).get_proxy().ConfigureStreams( self.streamDescList )

            #
            # Update venue clients being led with stream descriptions
            #
            for profile in self.followerProfiles.values():
                Client.Handle( profile.venueClientUri ).get_proxy().wsEnterVenue( URL )
                
        except:
            print "Exception in EnterVenue : ", sys.exc_type, sys.exc_value
        
    def ExitVenue( self ):
        """
        ExitVenue removes this client from the specified venue.
        """
        self.heartbeatTask.stop()
        self.venueProxy.Exit( self.privateId )
        self.eventClient.Stop()        
        self.__InitVenueData__()

    def GetVenue( self ):
        """
        GetVenue gets the venue the client is currently in.
        """
        return self.venueUri
        
    def GetHomeVenue( self ):
        """
        GetHomeVenue returns the default venue for this venue client.
        """
        return self.homeVenue
        
    def SetHomeVenue( self, venueURL):
        """
        SetHomeVenue sets the default venue for this venue client.
        """
        self.homeVenue = venueURL
        
    def Follow( self, venueClientUri ):
        """
        Follow tells this venue client to follow the node
        specified.
        """
        Client.Handle( venueClientUri ).get_proxy().wsLead( self.profile )

    def Unfollow( self, venueClientUri ):
        """
        Unfollow tells this venue client to stop following
        the node specified.
        """
        Client.Handle( venueClientUri ).get_proxy().wsUnlead( self.profile )

    def Lead( self, clientProfile):
        """
        Lead tells this venue client to drag the specified
        node with it.
        """
        self.followerProfiles[clientProfile.publicId] = clientProfile

    def Unlead( self, clientProfile):
        """
        Unlead tells this venue client to stop dragging the specified
        node with it.
        """
        for profile in self.followerProfiles.values():
            if profile.publicId == clientProfile.publicId:
                del self.followerProfiles[clientProfile.publicId]

    def SetNodeServiceUri( self, nodeServiceUri ):
        """
        Bind the given node service to this venue client
        """
        self.nodeServiceUri = nodeServiceUri

    #
    # Web Service methods
    #

    def wsSetProfile(self, connectionInfo, profile):
        self.SetProfile( profile )
    wsSetProfile.pass_connection_info = 1
    wsSetProfile.soap_export_as = "wsSetProfile"

    def wsEnterVenue(self, connectionInfo, venueUri ):
        try:
            self.EnterVenue( venueUri )
        except:
            print "EXception in wsEnterVenue ", sys.exc_type, sys.exc_value
    wsEnterVenue.pass_connection_info = 1
    wsEnterVenue.soap_export_as = "wsEnterVenue"
        
    def wsExitVenue(self, connectionInfo ):
        self.ExitVenue()
    wsExitVenue.pass_connection_info = 1
    wsExitVenue.soap_export_as = "wsExitVenue"
        
    def wsGetVenue(self, connectionInfo):
        return self.GetVenue()
    wsGetVenue.pass_connection_info = 1
    wsGetVenue.soap_export_as = "wsGetVenue"
        
    def wsGetHomeVenue(self, connectionInfo ):
        return self.GetHomeVenue()
    wsGetHomeVenue.pass_connection_info = 1
    wsGetHomeVenue.soap_export_as = "wsGetHomeVenue"
        
    def wsSetHomeVenue(self, connectionInfo, venueUri ):
        self.SetHomeVenue( venueUri )
    wsSetHomeVenue.pass_connection_info = 1
    wsSetHomeVenue.soap_export_as = "wsSetHomeVenue"
        
    def wsLead( self, connectionInfo, clientProfile):
        self.Lead( clientProfile )
    wsLead.pass_connection_info = 1
    wsLead.soap_export_as = "wsLead"

    def wsUnlead( self, connectionInfo, clientProfile):
        self.Unlead( clientProfile )
    wsUnlead.pass_connection_info = 1
    wsUnlead.soap_export_as = "wsUnlead"

    def wsFollow(self, connectionInfo, venueClientUri ):
        self.Follow( venueClientUri )
    wsFollow.pass_connection_info = 1
    wsFollow.soap_export_as = "wsFollow"

    def wsUnfollow(self, connectionInfo, venueClientUri ):
        self.Unfollow( venueClientUri )
    wsUnfollow.pass_connection_info = 1
    wsUnfollow.soap_export_as = "wsUnfollow"

    def wsSetNodeServiceUri( self, connectionInfo, nodeServiceUri ):
        self.SetNodeServiceUri( nodeServiceUri )
    wsSetNodeServiceUri.pass_connection_info = 1
    wsSetNodeServiceUri.soap_export_as = "wsSetNodeServiceUri"