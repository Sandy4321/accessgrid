#-----------------------------------------------------------------------------
# Name:        Descriptions.py
# Purpose:     Classes for Access Grid Object Descriptions
#
# Author:      Ivan R. Judson
#
# Created:     2002/11/12
# RCS-ID:      $Id: Descriptions.py,v 1.64 2004-08-18 20:17:09 lefvert Exp $
# Copyright:   (c) 2002
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
"""
__revision__ = "$Id: Descriptions.py,v 1.64 2004-08-18 20:17:09 lefvert Exp $"
__docformat__ = "restructuredtext en"

import string
import types

from AccessGrid.GUID import GUID
from AccessGrid.NetworkLocation import MulticastNetworkLocation
from AccessGrid.NetworkLocation import UnicastNetworkLocation
from AccessGrid.NetworkLocation import ProviderProfile
from AccessGrid.Types import Capability
from AccessGrid.Types import AGResource, AGVideoResource
from AccessGrid.ServiceCapability import ServiceCapability

from AccessGrid.ClientProfile import ClientProfile
class ObjectDescription:
    """
    An object description has four parts:
        id : string
        name : string
        description : string
        uri : uri (string)
    """
    def __init__(self, name, description = None, uri = None,
                 oid = None):

        # Catch annoying None case
        if oid != None:
            self.id = oid
        else:
            self.id = str(GUID())

        self.name = name
        self.description = description
        self.uri = uri
        
    def __repr__(self):
        classpath = string.split(str(self.__class__), '.')
        classname = classpath[-1]
        return "%s: %s" % (classname, str(self.__dict__))

    def AsINIBlock(self):
        string = "\n[%s]\n" % self.id
        string += "name : %s\n" % self.name
        if self.description != None:
            string += "description : %s\n" % self.description
        if self.uri != None:
            string += "uri : %s\n" % self.uri

        return string

    def SetId(self, oid):
        self.id = oid
        
    def GetId(self):
        return self.id
    
    def SetName(self, name):
        self.name = name
        
    def GetName(self):
        return self.name
    
    def SetDescription(self, description):
        self.description = description
        
    def GetDescription(self):
        return self.description
    
    def SetURI(self, uri):
        self.uri = uri
        
    def GetURI(self):
        return self.uri

class BadDataDescription(Exception):
    pass

class DataDescription(ObjectDescription):
    """
    A Data Description represents data within a venue.

    Each description object represents a single file. (We assume that
    the venue-resident data server does not support directory hierarchies).

    """

    #
    # Status values
    #

    STATUS_INVALID = "invalid"
    STATUS_REFERENCE = "reference"
    STATUS_PRESENT = "present"
    STATUS_PENDING = "pending"
    STATUS_UPLOADING = "uploading"
   
    valid_status = [STATUS_INVALID, STATUS_REFERENCE, STATUS_PRESENT,
                    STATUS_PENDING, STATUS_UPLOADING]

    class InvalidStatus(Exception):
        pass
    
    def __init__(self, name):
        ObjectDescription.__init__(self, name)

        self.status = self.STATUS_INVALID
        self.size = 0
        self.checksum = None
        self.owner = None
        self.type = None # this is venue data
        self.lastModified = None

    def SetLastModified(self, date):
        self.lastModified = date

    def GetLastModified(self):
        return self.lastModified

    def SetType(self, type):
        self.type = type

    def GetType(self):
        return self.type

    def SetStatus(self, status):
        if status not in self.valid_status:
            raise self.InvalidStatus(status)
        self.status = status

    def GetStatus(self):
        return self.status

    def SetSize(self, size):
        if type(size) != int:
            raise TypeError("Size must be an int.")
        self.size = size

    def GetSize(self):
        return self.size

    def SetChecksum(self, checksum):
        self.checksum = checksum

    def GetChecksum(self):
        return self.checksum

    def SetOwner(self, owner):
        self.owner = owner

    def GetOwner(self):
        return self.owner

    def AsINIBlock(self):
        string = ObjectDescription.AsINIBlock(self)
        string += "status : %s\n" % self.GetStatus()
        string += "size : %d\n" % self.GetSize()
        string += "checksum : %s\n" % self.GetChecksum()
        string += "owner: %s\n" % self.GetOwner()
        string += "type: %s\n" % self.GetType()
        string += 'lastModified: %s\n' % self.GetLastModified()

        return string

class ConnectionDescription(ObjectDescription):
    """
    A Connection Description is used to represent the 
    connection from the current venue to another venue.
    """
    pass    

class VenueDescription(ObjectDescription):
    """
    A Venue Description is used to represent a Venue.
    """
    def __init__(self, name=None, description=None, encryptionInfo=(0,''),
                 connectionList=[], staticStreams=[], oid = None,
                 uri=None):

        ObjectDescription.__init__(self, name, description, uri, oid)
        self.streams = list()
        self.encryptMedia = 0
        self.encryptionKey = None
        self.encryptMedia = encryptionInfo[0]
        
        if self.encryptMedia:
            self.encryptionKey = encryptionInfo[1]
        else:
            self.encryptionKey = None
           
        self.connections = connectionList
        self.streams = staticStreams
    
    def AsINIBlock(self):
        string = ObjectDescription.AsINIBlock(self)
        if self.encryptMedia:
            string += "encryptionKey : %s\n" % self.encryptionKey
        clist = ":".join(map(lambda conn: conn.GetId(),
                             self.connections))
        string += "connections : %s\n" % clist
        slist = ":".join(map(lambda stream: stream.GetId(),
                             self.streams))
        string += "streams : %s\n" % slist
        string += "\n".join(map(lambda conn: conn.AsINIBlock(),
                                self.connections))
        string += "\n".join(map(lambda stream: stream.AsINIBlock(),
                                self.streams))
        return string

    def __repr__(self):
        return self.AsINIBlock()

class BadServiceDescription(Exception):
    pass


class ServiceDescription(ObjectDescription):
    """
    The Service Description is the Virtual Venue resident information
    about services users can interact with. This is an extension of
    the Object Description that adds a mimeType which should be a
    standard mime-type.
    """
    def __init__(self, name, description, uri, mimetype):   
        ObjectDescription.__init__(self, name, description, uri)   
        self.mimeType = mimetype   
    
    def SetMimeType(self, mimetype):   
        self.mimeType = mimetype   
            
    def GetMimeType(self):   
        return self.mimeType   

    def AsINIBlock(self):
        string = ObjectDescription.AsINIBlock(self)
        string += "mimeType: %s" % self.mimeType

        return string

class ApplicationCmdDescription:
    def __init__(self, appDesc, verb, cmd, senderProfile):   
        self.appDesc = appDesc
        self.verb = verb
        self.command = cmd
        self.profile = senderProfile
    
class ApplicationDescription(ObjectDescription):
    """
    The Service Description is the Virtual Venue resident information
    about services users can interact with. This is an extension of
    the Object Description that adds a mimeType which should be a
    standard mime-type.
    """
    def __init__(self, oid, name, description, uri, mimetype, startable=1):   
        ObjectDescription.__init__(self, name, description, uri, oid = oid)
        self.mimeType = mimetype   
        self.startable = startable
    
    def SetMimeType(self, mimetype):   
        self.mimeType = mimetype   
            
    def GetMimeType(self):   
        return self.mimeType   

    def AsINIBlock(self):
        string = ObjectDescription.AsINIBlock(self)
        string += "mimeType : %s\n" % self.mimeType
        string += "startable : %s\n" % self.startable
        
        return string

class BadApplicationDescription(Exception):
    pass
        
class StreamDescription( ObjectDescription ):
   """A Stream Description represents a stream within a venue"""
   def __init__( self, name=None, 
                 location=MulticastNetworkLocation(), 
                 capability=Capability(),
                 encryptionFlag=0, encryptionKey=None,
                 static=0):
      ObjectDescription.__init__( self, name, None, None)
      self.location = location
      self.capability = capability
      self.encryptionFlag = encryptionFlag
      self.encryptionKey = encryptionKey
      self.static = static
      self.networkLocations = []
      
      if location:
          self.AddNetworkLocation(location)
          
   def AddNetworkLocation(self,networkLocation):
       """
       Add the specified network location to the list
       
       Note: This method overwrites the network location id 
             in the incoming network location
       """
       networkLocation.id = str(GUID())
       self.networkLocations.append(networkLocation)
       return networkLocation.id
       
   def RemoveNetworkLocation(self, networkLocationId):
       """
       Remove the network location with specified id
       """
       for networkLocation in self.networkLocations:
           if networkLocation.id == networkLocationId:
               self.networkLocations.remove(networkLocation)

   def AsINIBlock(self):
       # Make sure xml capabilities are stored properly
       
       string = ObjectDescription.AsINIBlock(self)
       string += "encryptionFlag : %s\n" % self.encryptionFlag
       if self.encryptionFlag:
           string += "encryptionKey : %s\n" % self.encryptionKey
       string += "location : %s\n" % self.location
       string += "capability : %s\n" % self.capability

       return string
   
class AGServiceManagerDescription:
    def __init__( self, name, uri ):
        self.name = name
        self.uri = uri

class AGServiceDescription:
    def __init__( self, name, description, uri, capabilities,
                  resource, executable, serviceManagerUri,
                  servicePackageFile, version ):
        self.name = name
        self.description = description

        self.uri = uri

        self.capabilities = capabilities
        self.resource = resource
        self.executable = executable
        self.serviceManagerUri = serviceManagerUri
        self.servicePackageFile = servicePackageFile
        self.version = version

class AGNetworkServiceDescription:
    def __init__(self, name, description, url, venues, inCapabilities, outCapabilities, version):
        self.name = name
        self.description = description
        self.url = url
        self.version = version
        self.venues = venues
        
        self.inCapabilities = inCapabilities
        self.outCapabilities = outCapabilities

    def ToString(self):
        s = 'Name: %s, \nDescription %s, \nVersion %s, \nVenueUrl %s' %(self.name, self.description, self.version, self.venues)

        s = s + '\nIn Capabilities'
        for cap in self.inCapabilities:
            s = s + cap + '\n'
        s = s+ '\nOut Capabilities'
        for cap in self.outCapabilities:
            s = s + cap + '\n'

        return s
       
class AppParticipantDescription:
    def __init__(self, appId, clientProfile, status):
        self.appId = appId
        self.clientProfile = clientProfile
        self.status = status
        
class AppDataDescription:
    def __init__(self, appId, key, value):
        self.appId = appId
        self.key = key
        self.value = value
    
class VenueState:
    def __init__( self, uniqueId, name, description, uri, connections,
                  clients, data, eventLocation, textLocation, applications,
                  services, backupServer=None ):
        self.uniqueId = uniqueId
        self.name = name
        self.description = description
        self.uri = uri
        self.eventLocation = eventLocation
        self.textLocation = textLocation
        self.services = services
        self.backupServer = backupServer
        
        self.connections = dict()
        self.clients = dict()
        self.data = dict()
        self.applications = dict()
        self.services = dict()
        
        for connection in connections:
            self.connections[connection.uri] = connection
        for client in clients:
            # Pre-2.3 server compatability code
            if not client.connectionId:
                client.connectionId = client.venueClientURL

            self.clients[client.connectionId] = client
        for datum in data:
            self.data[datum.id] = datum
        for app in applications:
            self.applications[app.uri] = app
        for service in services:
            self.services[service.id] = service
    def SetUniqueId(self, uniqueId):
        self.uniqueId = uniqueId
    def GetUniqueId(self):
        return self.uniqueId
    def SetDescription( self, description ):
        self.description = description
    def GetDescription( self ):
        return self.description
    def SetName( self, name ):
        self.name = name
    def GetName( self ):
        return self.name
    def SetUri( self, uri ):
        self.uri = uri
    def GetUri( self ):
        return self.uri
    def AddUser( self, userProfile ):
        self.clients[userProfile.connectionId] = userProfile
    def RemoveUser( self, userProfile ):
        if userProfile.connectionId in self.clients.keys():
            del self.clients[userProfile.connectionId]
    def ModifyUser( self, userProfile ):
        if userProfile.connectionId in self.clients.keys():
            self.clients[userProfile.connectionId] = userProfile
    def GetUsers( self ):
        return self.clients.values()
    def AddConnection( self, connectionDescription ):
        self.connections[connectionDescription.uri] = connectionDescription
    def RemoveConnection( self, connectionDescription ):
        del self.connections[connectionDescription.uri]
    def SetConnections( self, connectionList ):
        for connection in connectionList:
            self.connections[connection.uri] = connection
    def GetConnections(self):
        return self.connections.values()
    def AddData( self, dataDescription ):
        self.data[dataDescription.id] = dataDescription
    def UpdateData( self, dataDescription ):
        self.data[dataDescription.id] = dataDescription
    def RemoveData( self, dataDescription ):
        del self.data[dataDescription.id]
    def GetData(self):
        return self.data.values()
    def AddService( self, serviceDescription ):
        self.services[serviceDescription.id] = serviceDescription
    def UpdateService(self, serviceDescription):
        self.services[serviceDescription.id] = serviceDescription            
    def RemoveService( self, serviceDescription ):
        if self.services.has_key(serviceDescription.id):
            del self.services[serviceDescription.id]  
        else:
            # Legacy code: Accomodate old (2.1.2 and before) servers,
            # which allocate a new id when the service description goes
            # through them.
            for id,service in self.services.items():
                if service.name == serviceDescription.name:
                    del self.services[id]
    def GetServices(self):
        return self.services.values()
    def AddApplication( self, applicationDescription ):
        self.applications[applicationDescription.uri] = applicationDescription
    def UpdateApplication(self, applicationDescription):
        self.applications[applicationDescription.uri] = applicationDescription
    def RemoveApplication( self, applicationDescription ):
        self.applications[applicationDescription.uri] = applicationDescription
    def GetApplications(self):
        return self.applications.values()
    def SetEventLocation( self, eventLocation ):
        self.eventLocation = eventLocation
    def GetEventLocation( self ):
        return self.eventLocation
    def SetTextLocation( self, textLocation ):
        self.textLocation = textLocation
    def GetTextLocation( self ):
        return self.textLocation

#
#
#
#
#
def CreateCapability(capabilityStruct):
    # Old capability
    cap = Capability(capabilityStruct.role,capabilityStruct.type)

    # Add new capability as xml document.
    if hasattr(capabilityStruct, 'xml') and capabilityStruct.xml:
        cap.xml = capabilityStruct.xml
    
    if hasattr(capabilityStruct.parms,"_asdict"):
        parmsdict = capabilityStruct.parms._asdict()
        for k,v in parmsdict.items():
            cap.parms[k] = v
    else:
        cap.parms = dict()
    return cap

def CreateClientProfile( clientProfileStruct ):
    """
    Create a client profile from a SOAP struct
    (this function should be removed when we have 
    WSDL support)
    """
    from AccessGrid.Types import Capability

    clientProfile = ClientProfile()

    clientProfile.distinguishedName = clientProfileStruct.distinguishedName
    clientProfile.email = clientProfileStruct.email
    clientProfile.homeVenue = clientProfileStruct.homeVenue
    clientProfile.icon = clientProfileStruct.icon
    clientProfile.location = clientProfileStruct.location
    clientProfile.name = clientProfileStruct.name
    clientProfile.phoneNumber = clientProfileStruct.phoneNumber
    clientProfile.privateId = clientProfileStruct.privateId
    clientProfile.profileFile = clientProfileStruct.profileFile
    clientProfile.profileType = clientProfileStruct.profileType
    clientProfile.publicId = clientProfileStruct.publicId
    clientProfile.techSupportInfo = clientProfileStruct.techSupportInfo
    clientProfile.venueClientURL = clientProfileStruct.venueClientURL
    if hasattr(clientProfileStruct,'connectionId'):
        clientProfile.connectionId = clientProfileStruct.connectionId
    else:
        # Pre-2.3 venue client (legacy, remove when breaking compatability)
        clientProfile.connectionId = clientProfileStruct.venueClientURL

    # convert capabilities from structtypes to objects
    capList = []
   
    for cap in clientProfileStruct.capabilities:
        capList.append(CreateCapability(cap))

    clientProfile.capabilities = capList

    return clientProfile

def CreateDataDescription(dataDescStruct):
    """
    """
    dd = DataDescription(dataDescStruct.name)
    dd.SetId(dataDescStruct.id)
    dd.SetName(dataDescStruct.name)
    dd.SetDescription(dataDescStruct.description)
    dd.SetURI(dataDescStruct.uri)
    if dataDescStruct.type == '':
        dd.SetType(None)
    else:
        dd.SetType(dataDescStruct.type)
    dd.SetStatus(dataDescStruct.status)
    dd.SetSize(dataDescStruct.size)
    dd.SetChecksum(dataDescStruct.checksum)
    dd.SetOwner(dataDescStruct.owner)
    try:
        dd.SetLastModified(dataDescStruct.lastModified)
    except:
        # This is an old description, has no lastModified parameter
        pass
    
    return dd

def CreateStreamDescription( streamDescStruct ):
    #cap = Capability( streamDescStruct.capability.role, 
    #                  streamDescStruct.capability.type )
    cap = CreateCapability(streamDescStruct.capability)

    streamDescription = StreamDescription( streamDescStruct.name, 
                                           None,
                                           cap,
                                           streamDescStruct.encryptionFlag,
                                           streamDescStruct.encryptionKey,
                                           streamDescStruct.static)
                                           
    # stream id must not change in this conversion
    streamDescription.id = streamDescStruct.id
    
    # set the location explicitly, to avoid 
    # netloc management in StreamDesc init
    streamDescription.location = CreateNetworkLocation(streamDescStruct.location)
    
    # Convert network locations and add to stream description
    for netloc in streamDescStruct.networkLocations:
        streamDescription.AddNetworkLocation(CreateNetworkLocation(netloc))
    
    return streamDescription

def CreateServiceDescription(serviceDescStruct):
    serviceDescription = ServiceDescription( serviceDescStruct.name,    
                                             serviceDescStruct.description,
                                             serviceDescStruct.uri,
                                             serviceDescStruct.mimeType )

    serviceDescription.SetId(serviceDescStruct.id)

    return serviceDescription

def CreateApplicationDescription(appDescStruct):
    # To be compatible with pre 2.2 code.
    if not hasattr(appDescStruct, 'startable'):
        appDescStruct.startable = 1

    appDescription = ApplicationDescription( appDescStruct.id,
                                             appDescStruct.name,    
                                             appDescStruct.description,
                                             appDescStruct.uri,
                                             appDescStruct.mimeType,
                                             appDescStruct.startable )

    appDescription.SetId(appDescStruct.id)

    return appDescription

def CreateConnectionDescription(connDescStruct):
    connDesc = ConnectionDescription(connDescStruct.name,
                                     connDescStruct.description,
                                     connDescStruct.uri,
                                     connDescStruct.id)
    return connDesc

def CreateVenueDescription(venueDescStruct):
    clist = []
    for c in venueDescStruct.connections:
        # THIS IS ICKY TOO
        if c != '\n':
            clist.append(ConnectionDescription(c.name, c.description, c.uri))

    slist = []
    for s in venueDescStruct.streams:
        slist.append(CreateStreamDescription(s))

    vdesc = VenueDescription(venueDescStruct.name, venueDescStruct.description,
                             (venueDescStruct.encryptMedia,
                              venueDescStruct.encryptionKey), clist, slist)

    vdesc.SetId(venueDescStruct.id)
    vdesc.SetURI(venueDescStruct.uri)
    
    return vdesc

def CreateVenueState(venueStateStruct):
    connectionList = list()
    clientList = list()
    dataList = list()
    applicationList = list()
    serviceList = list()
    
    for conn in venueStateStruct.connections:
        connectionList.append(CreateConnectionDescription(conn))

    for client in venueStateStruct.clients:
        clientList.append( CreateClientProfile(client) )

    for data in venueStateStruct.data:
        dataList.append( CreateDataDescription(data) )
        
    for application in venueStateStruct.applications:
        applicationList.append(CreateApplicationDescription(application))

    for service in venueStateStruct.services:
        serviceList.append(CreateServiceDescription(service))

    # I hate retrofitted code.
    if not hasattr(venueStateStruct, 'backupServer'):
        venueStateStruct.backupServer = None
        
    venueState = VenueState(venueStateStruct.uniqueId,
                            venueStateStruct.name,
                            venueStateStruct.description,
                            venueStateStruct.uri,
                            connectionList, clientList, dataList,
                            venueStateStruct.eventLocation,
                            venueStateStruct.textLocation,
                            applicationList, serviceList,
                            venueStateStruct.backupServer)    
    return venueState


def CreateAGServiceManagerDescription(svcMgrDescStruct):
    svcMgrDesc = AGServiceManagerDescription(svcMgrDescStruct.name,
                                           svcMgrDescStruct.uri)
    return svcMgrDesc

def CreateAGServiceDescription(svcDescStruct):

    resource = CreateResource(svcDescStruct.resource)
    capabilities = []
   
    for cap in svcDescStruct.capabilities:
        capabilities.append( CreateCapability(cap))
    svcDesc = AGServiceDescription(svcDescStruct.name, 
                                   svcDescStruct.description, 
                                   svcDescStruct.uri, 
                                   capabilities,
                                   resource, 
                                   svcDescStruct.executable, 
                                   svcDescStruct.serviceManagerUri,
                                   svcDescStruct.servicePackageFile,
                                   svcDescStruct.version )
    return svcDesc

def CreateAGNetworkServiceDescription(svcDescStruct):
    svcDesc = AGNetworkServiceDescription(svcDescStruct.name, 
                                          svcDescStruct.description, 
                                          svcDescStruct.url,
                                          svcDescStruct.venues,
                                          svcDescStruct.inCapabilities,
                                          svcDescStruct.outCapabilities,
                                          svcDescStruct.version)
    return svcDesc


def CreateResource(rscStruct):
    if rscStruct:
        if rscStruct.type == 'video':
            rsc = AGVideoResource(rscStruct.type,
                                  rscStruct.resource,
                                  rscStruct.role,
                                  rscStruct.portTypes)
        else:
            rsc = AGResource(rscStruct.type,
                             rscStruct.resource,
                             rscStruct.role)
    else:
        rsc = AGResource()
    return rsc

def CreateNetworkLocation(networkLocationStruct):
    if networkLocationStruct.type == UnicastNetworkLocation.TYPE:
        networkLocation = UnicastNetworkLocation(networkLocationStruct.host,
                                                 networkLocationStruct.port)
    elif networkLocationStruct.type == MulticastNetworkLocation.TYPE:
        networkLocation = MulticastNetworkLocation(networkLocationStruct.host,
                                                 networkLocationStruct.port,
                                                 networkLocationStruct.ttl)
    else:
        raise Exception, "Unknown network location type %s" % (networkLocationStruct.type,)
    
    networkLocation.profile = ProviderProfile(networkLocationStruct.profile.name,
                                              networkLocationStruct.profile.location)                                                                                                 
    networkLocation.id = networkLocationStruct.id
    networkLocation.privateId = networkLocationStruct.privateId
    return networkLocation


def CreateParameter( parmstruct ):
    """
    Object factory to create parameter instances from SOAPStructs
    """
    from AGParameter import OptionSetParameter, TextParameter
    from AGParameter import RangeParameter, ValueParameter
    if parmstruct.type == OptionSetParameter.TYPE:
        parameter = OptionSetParameter( parmstruct.name, parmstruct.value, parmstruct.options )
    elif parmstruct.type == RangeParameter.TYPE:
        parameter = RangeParameter( parmstruct.name, parmstruct.value, parmstruct.low, parmstruct.high )
    elif parmstruct.type == ValueParameter.TYPE:
        parameter = ValueParameter( parmstruct.name, parmstruct.value )
    elif parmstruct.type == TextParameter.TYPE:
        parameter = TextParameter( parmstruct.name, parmstruct.value )
    else:
        raise TypeError("Unknown parameter type:", parmstruct.type )

    return parameter
