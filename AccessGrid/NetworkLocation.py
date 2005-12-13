#-----------------------------------------------------------------------------
# Name:        NetworkLocation.py
# Purpose:     This object encapsulates the network configuration gunk.
#
# Author:      Ivan R. Judson
#
# Created:     2002/13/12
# RCS-ID:      $Id: NetworkLocation.py,v 1.18 2005-12-13 23:04:20 lefvert Exp $
# Copyright:   (c) 2003
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
"""
__revision__ = "$Id: NetworkLocation.py,v 1.18 2005-12-13 23:04:20 lefvert Exp $"
__docformat__ = "restructuredtext en"


class ProviderProfile:
    """
    ProviderProfile contains information to identify the provider
    of a network location. 
    """
    def __init__(self,name="",location=""):
        self.name = name
        self.location = location

class NetworkLocation:
    """
    The Network Locations are simply python objects to manage network
    information. We derive two types, unicast and multicast. It's probably more
    correct to derive IP4Uni and IP4Multi and IP6Uni and IP6Multi, but that's
    an exercise for later.
    """
    TYPE = 'any'
    host = ''
    port = 0

    def __init__(self, host=None, port=-1):
        self.host = host
        if type(port) != int:
            raise TypeError("Network Location Port must be an int.")
        else:
            self.port = port
        self.type = self.TYPE
        self.id = ""
        self.privateId = ""
        self.profile = ProviderProfile("","")

    def SetHost(self, host):
        self.host = host

    def GetHost(self):
        return self.host

    def SetPort(self, port):
        if type(port) != int:
            raise TypeError("Network Location Port must be an int.")
        else:
            self.port = port

    def GetPort(self):
        return self.port

    def GetType(self):
        return self.type

    def SetType(self, type):
        self.type = type

    def __repr__(self):
        string = "%s %d" % (self.host, self.port)
        return string

class UnicastNetworkLocation(NetworkLocation):
    """
    Unicast network location encapsulates the configuration information about
    a unicast network connection.
    """
    TYPE = 'unicast'

    def __repr__(self):
        string = "%s %s %d" % (self.type, self.host, self.port)
        return string


class MulticastNetworkLocation(NetworkLocation):
    """
    Multicast network location encapsulates the configuration information about
    a multicsat network connection.
    """
    TYPE = 'multicast'
    ttl = 0

    def __init__(self, host=None, port=0, ttl=0):
        if type(ttl) != int:
            raise TypeError("Multicast Network Location TTL must be an int.")
        else:
            self.ttl = ttl

        NetworkLocation.__init__(self, host, port)

    def __repr__(self):
        string = "%s %s %d %d" % (self.type, self.host, self.port, self.ttl)
        return string

    def SetTTL(self, ttl):
        if type(ttl) != int:
            raise TypeError("Multicast Network Location TTL must be an int.")
        else:
            self.ttl = ttl

    def GetTTL(self):
        return self.ttl
