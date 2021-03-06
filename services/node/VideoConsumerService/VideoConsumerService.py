#-----------------------------------------------------------------------------
# Name:        VideoConsumerService.py
# Purpose:
# Created:     2003/06/02
# RCS-ID:      $Id: VideoConsumerService.py,v 1.17 2007/09/12 07:01:56 douglask Exp $
# Copyright:   (c) 2002
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
import sys, os
import wx
try:    import _winreg
except: pass

from AccessGrid import Toolkit
import socket
import select

from AccessGrid.Descriptions import Capability
from AccessGrid.AGService import AGService
from AccessGrid.AGParameter import ValueParameter, OptionSetParameter, RangeParameter
from AccessGrid.Platform import IsWindows, IsLinux, IsFreeBSD, IsOSX
from AccessGrid.Platform.Config import AGTkConfig, UserConfig, SystemConfig
from AccessGrid.NetworkLocation import MulticastNetworkLocation
from AccessGrid.UIUtilities import GetScreenWidth

class VideoConsumerService( AGService ):

    tileOptions = [ '1', '2', '3', '4', '5', '6', '7', '8', '9', '10' ]

    def __init__( self ):
        AGService.__init__( self )
        self.capabilities = [ Capability( Capability.CONSUMER,
                                          Capability.VIDEO,
                                          "H261",
                                          90000, self.id) ]

        if IsWindows():
            vic = "vic.exe"
        else:
            vic = "vic"

        self.executable = os.path.join(os.getcwd(),vic)
        if not os.path.isfile(self.executable):
            self.executable = vic

        self.sysConf = SystemConfig.instance()

        self.profile = None
        self.windowGeometry = None

        self.startPriority = '7'
        self.startPriorityOption.value = self.startPriority

        # Set configuration parameters
        self.tiles = OptionSetParameter( "Thumbnail Columns", "4", VideoConsumerService.tileOptions )
        self.positionWindow = OptionSetParameter( 'Position Window', 'Justify Left', ['Off', 'Justify Left', 'Justify Right'])
        
        self.configuration.append( self.tiles )
        self.configuration.append( self.positionWindow)

        if IsWindows():
            try:
                import win32api

                # get number of processors
                systemInfo = win32api.GetSystemInfo()
                numprocs = systemInfo[5]
                self.allProcsMask = 2**numprocs-1

                self.procOptions = ['All']
                for i in range(numprocs):
                    self.procOptions.append(str(i+1))

                self.processorUsage = OptionSetParameter( "Processor usage", self.procOptions[0], self.procOptions )
                self.configuration.append( self.processorUsage )
            except:
                self.log.exception('Error initializing processor usage options')


    def __SetRTPDefaults(self, profile):
        """
        Set values used by rat for identification
        """
        if profile == None:
            self.log.exception("Invalid profile (None)")
            raise Exception, "Can't set RTP Defaults without a valid profile."

        if IsLinux() or IsOSX() or IsFreeBSD():
            try:
                rtpDefaultsFile=os.path.join(os.environ["HOME"], ".RTPdefaults")
                rtpDefaultsText="*rtpName: %s\n*rtpEmail: %s\n*rtpLoc: %s\n*rtpPhone: \
                                 %s\n*rtpNote: %s\n"
                rtpDefaultsFH=open( rtpDefaultsFile,"w")
                rtpDefaultsFH.write( rtpDefaultsText % ( profile.name,
                                       profile.email,
                                       profile.location,
                                       profile.phoneNumber,
                                       profile.publicId ) )
                rtpDefaultsFH.close()
            except:
                self.log.exception("Error writing RTP defaults file: %s", rtpDefaultsFile)

        elif IsWindows():
            try:
                # Set RTP defaults according to the profile
                k = _winreg.CreateKey(_winreg.HKEY_CURRENT_USER,
                                    r"Software\Mbone Applications\common")

                # Vic reads these values (with '*')
                _winreg.SetValueEx(k, "*rtpName", 0,
                                   _winreg.REG_SZ, profile.name)
                _winreg.SetValueEx(k, "*rtpEmail", 0,
                                   _winreg.REG_SZ, profile.email)
                _winreg.SetValueEx(k, "*rtpPhone", 0,
                                   _winreg.REG_SZ, profile.phoneNumber)
                _winreg.SetValueEx(k, "*rtpLoc", 0,
                                   _winreg.REG_SZ, profile.location)
                _winreg.SetValueEx(k, "*rtpNote", 0,
                                   _winreg.REG_SZ, str(profile.publicId) )
                _winreg.CloseKey(k)
            except:
                self.log.exception("Error writing RTP defaults to registry")
        else:
            self.log.error("No support for platform: %s", sys.platform)
            
        
    def Start( self ):
        """Start service"""
        try:

            # Set processor affinity (windows only)
            if IsWindows():
                try:
                    if self.processorUsage.value == 'All':
                        self.log.info('Setting processor affinity to all processors')
                        SystemConfig.instance().SetProcessorAffinity(self.allProcsMask)
                    else:
                        val = 2**(int(self.processorUsage.value)-1)
                        self.log.info('Ssetting processor affinity : use processor %s', self.processorUsage.value)
                        SystemConfig.instance().SetProcessorAffinity(int(self.processorUsage.value))
                except:
                    self.log.exception("Exception setting processor affinity")

            # Enable firewall
            self.sysConf.AppFirewallConfig(self.executable, 1)

            # Start the service; in this case, store command line args
            # in a list and let the superclass _Start the service
            options = []
            if self.streamDescription.name and \
                   len(self.streamDescription.name.strip()) > 0:
                options.append( "-C" )
                options.append( self.streamDescription.name )
            if self.streamDescription.encryptionFlag != 0:
                options.append( "-K" )
                options.append( self.streamDescription.encryptionKey )
            # Check whether the network location has a "type"
            # attribute Note: this condition is only to maintain
            # compatibility between older venue servers creating
            # network locations without this attribute and newer
            # services relying on the attribute; it should be removed
            # when the incompatibility is gone
            if self.streamDescription.location.__dict__.has_key("type"):
                if self.streamDescription.location.type == MulticastNetworkLocation.TYPE:
                    options.append( "-t" )
                    options.append( '%d' % ( self.streamDescription.location.ttl ) )

            # Set name and email on command line, in case rtp defaults
            # haven't been written (to avoid vic prompting for
            # name/email)
            name=email="Participant"
            if self.profile:
                name = self.profile.name
                email = self.profile.email
            options.append('-XrtpName=%s' % (name,))
            options.append('-XrtpEmail=%s' % (email,))

            # Set some tk resources to customize vic
            # - this is a consumer, so disable device selection in vic
            options.append('-XrecvOnly=1')
            # - set drop time to something reasonable
            options.append('-XsiteDropTime=5')

            if not self.positionWindow.value == 'Off':
                # - set vic window geometry
                try:
                    
                    if not self.windowGeometry:
                        h = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_Y)
                        w_sys = wx.SystemSettings.GetMetric(wx.SYS_SCREEN_X)
                        try:
                            w = GetScreenWidth(w_sys,h)
                        except ValueError:
                            self.log.debug('Error computing screen width; using system screen width %d', w_sys)
                            w = w_sys
                        window_width = w-300
                        window_height = 300
                        window_x = 300
                        window_y = h-375
                        border_w = wx.SystemSettings_GetMetric(wx.SYS_FRAMESIZE_X)
                        if border_w > 0:
                            window_width -= 4*border_w
                            window_x += 2*border_w
                        self.windowGeometry = (window_width,window_height,window_x,window_y)
                    if self.positionWindow.value == 'Justify Left':
                        options.append('-Xgeometry=%dx%d+%d+%d' % self.windowGeometry)
                    else:
                        options.append('-Xgeometry=%dx%d-%d+%d' % self.windowGeometry)
                except:
                    self.log.exception('Error calculating window placement')

            # - set number of columns of thumbnails to display
            options.append('-Xtile=%s' % self.tiles.value)
                    
            # Add address/port options (these must occur last; don't
            # add options beyond here)
            options.append( '%s/%d' % (self.streamDescription.location.host,
                                       self.streamDescription.location.port))

            # Create a socket, send some data out, and listen for incoming data
            try:
                host = self.streamDescription.location.host
                port = self.streamDescription.location.port
                timeout = 1
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if IsOSX():
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                s.bind(('', port))
                s.sendto('qwe',(host,port))
                fdList = []
                while not fdList:
                    fdList = select.select([s.fileno()],[],[],timeout)
                s.close()
                s = None
            except:
                self.log.warn("Failed attempt to open firewall by sending data out on video port; continuing anyway")
                if s:
                    s.close()
                    s = None

            self.log.info("Starting VideoConsumerService")
            self.log.info(" executable = %s" % self.executable)
            self.log.info(" options = %s" % options)
            self._Start( options )
        except:
            self.log.exception("Exception in VideoConsumerService.Start")
            raise Exception("Failed to start service")

    def Stop( self ):
        """Stop the service"""

        # vic doesn't die easily (on linux at least), so force it to stop
        AGService.ForceStop(self)

        # Disable firewall
        self.sysConf.AppFirewallConfig(self.executable, 0)

    def SetStream( self, streamDescription ):
        """Configure the Service according to the StreamDescription"""

        ret = AGService.ConfigureStream( self, streamDescription )
        if ret and self.started:
            # service is already running with this config; ignore
            return

        # if started, stop
        if self.started:
            self.Stop()

        # if enabled, start
        if self.enabled:
            self.Start()

    def SetIdentity(self, profile):
        """
        Set the identity of the user driving the node
        """
        self.log.info("SetIdentity: %s %s", profile.name, profile.email)
        self.profile = profile
        self.__SetRTPDefaults(profile)

if __name__ == '__main__':

    from AccessGrid.interfaces.AGService_interface import AGService as AGServiceI
    from AccessGrid.AGService import RunService

    service = VideoConsumerService()
    serviceI = AGServiceI(service)
    RunService(service,serviceI)
