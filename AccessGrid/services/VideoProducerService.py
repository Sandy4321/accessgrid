#-----------------------------------------------------------------------------
# Name:        VideoProducerService.py
# Purpose:     
#
# Author:      Thomas D. Uram
#
# Created:     2003/06/02
# RCS-ID:      $Id: VideoProducerService.py,v 1.6 2003-02-26 23:15:01 turam Exp $
# Copyright:   (c) 2002
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
import sys
import os
from AccessGrid.hosting.pyGlobus.Server import Server
from AccessGrid.Types import Capability
from AccessGrid.AGService import AGService
from AccessGrid.AGParameter import ValueParameter, OptionSetParameter, RangeParameter


vicstartup="""option add Vic.muteNewSources true startupFile
option add Vic.maxbw 6000 startupFile
option add Vic.bandwidth %d startupFile
option add Vic.framerate %d startupFile
option add Vic.quality 85 startupFile
option add Vic.defaultFormat %s startupFile
option add Vic.inputType NTSC startupFile
set device \"%s\"
set defaultPort($device) %s
option add Vic.device $device startupFile
option add Vic.transmitOnStartup true startupFile
option add Vic.defaultTTL 127 startupFile
proc user_hook {} {
}
"""



class VideoProducerService( AGService ):

   encodings = [ "h261" ]

   def __init__( self ):
      print self.__class__, ".init"
      AGService.__init__( self )

      self.capabilities = [ Capability( Capability.PRODUCER, Capability.VIDEO ) ]
      self.executable = "vic"

      #
      # Set configuration parameters
      #

      # note: the datatype of the port parameter changes when a resource is set!
      self.configuration["Port"] = ValueParameter( "Port", None ) 
      self.configuration["Encoding"] = OptionSetParameter( "Encoding", "h261", VideoProducerService.encodings )
      self.configuration["Bandwidth"] = RangeParameter( "Bandwidth", 800, 0, 3072 ) 
      self.configuration["Frame Rate"] = RangeParameter( "Frame Rate", 25, 1, 30 ) 
      self.configuration["Stream Name"] = ValueParameter( "Stream Name", "Video" )


   def Start( self ):
      __doc__ = """Start service"""
      try:
         
         #
         # Resolve assigned resource to a device understood by vic
         #
         vicDevice = self.resource.resource

         #
         # Write vic startup file
         #
         startupfile = 'VideoProducerService_%d.vic' % ( os.getpid() )
         f = open(startupfile,"w")
         f.write( vicstartup % (self.configuration["Bandwidth"].value, 
                                    self.configuration["Frame Rate"].value, 
                                    self.configuration["Encoding"].value, 
                                    vicDevice,
                                    self.configuration["Port"].value  ) )
         f.close()


         # 
         # Start the service; in this case, store command line args in a list and let
         # the superclass _Start the service
         print "Start service"
         print "Location : ", self.streamDescription.location.host, self.streamDescription.location.port, self.streamDescription.location.ttl
         options = []
         options.append( "-u" )
         options.append( startupfile ) 
         options.append( "-C" )
         options.append( self.configuration["Stream Name"].value )
         if self.streamDescription.encryptionKey != 0:
            options.append( "-K" )
            options.append( self.streamDescription.encryptionKey )
         options.append( "-t" )
         options.append( '%d' % (self.streamDescription.location.ttl) )
         options.append( '%s/%d' % ( self.streamDescription.location.host, 
                                        self.streamDescription.location.port) )
         self._Start( options )
         print "pid = ", self.childPid
      except:
         print "Exception in VideoProducerService.Start", sys.exc_type, sys.exc_value
   Start.soap_export_as = "Start"


   def ConfigureStream( self, streamDescription ):
      """Configure the Service according to the StreamDescription, and stop and start rat"""
      AGService.ConfigureStream( self, streamDescription )

      # restart rat, since this is the only way to change the 
      # stream location (for now!)
      if self.started:
         self.Stop()
         self.Start()
   ConfigureStream.soap_export_as = "ConfigureStream"

   def SetResource( self, resource ):
      """Set the resource used by this service"""
      print " * ** * inside VideoProducerService.SetResource"
      self.resource = resource
      if "portTypes" in self.resource.__dict__.keys():
          self.configuration["Port"] = OptionSetParameter( "Port", self.resource.portTypes[0], 
      
   SetResource.soap_export_as = "SetResource"


def AuthCallback(server, g_handle, remote_user, context):
    return 1

if __name__ == '__main__':
   from AccessGrid.hosting.pyGlobus import Client
   import thread

   agService = VideoProducerService()
   server = Server( 0, auth_callback=AuthCallback )
   service = server.create_service_object()
   agService._bind_to_service( service )

   print "Register with the service manager ! "
   thread.start_new_thread( Client.Handle( sys.argv[2] ).get_proxy().RegisterService, 
                            ( sys.argv[1], agService.get_handle() ) )

   print "Starting server at", agService.get_handle()
   server.run()
