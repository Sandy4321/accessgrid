#-----------------------------------------------------------------------------
# Name:        Utilities.py
# Purpose:
#
# Author:      Everyone
#
# Created:     2003/23/01
# RCS-ID:      $Id: Utilities.py,v 1.24 2003-04-24 18:36:47 judson Exp $
# Copyright:   (c) 2003
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
import os
import string
import sys
import traceback
import ConfigParser
import time
from random import Random
import sha
import urllib
import mailcap

try:
    import _winreg
except:
    pass

from wxPython.wx import wxTheMimeTypesManager as mtm
from wxPython.wx import wxFileTypeInfo

from AccessGrid.Platform import Win32RegisterMimeType

def LoadConfig(fileName, config={}):
    """
    Returns a dictionary with keys of the form <section>.<option>
    and the corresponding values.
    This is from the python cookbook credit: Dirk Holtwick.
    """
    rconfig = config.copy()
    cp = ConfigParser.ConfigParser()
    cp.optionxform = str
    cp.read(fileName)
    for sec in cp.sections():
        for opt in cp.options(sec):
            rconfig[sec + "."+ opt] = string.strip(cp.get(sec, opt))
    return rconfig

def SaveConfig(fileName, config):
    """
    This method saves the current configuration out to the specified file.
    """
    cp = ConfigParser.ConfigParser()
    cp.optionxform = str
    for k in config.keys():
        (section, option) = string.split(k, '.')
        try:
            cp.set(section, option, config[k])
        except:
            cp.add_section(section)
            cp.set(section, option, config[k])

    cp.write(file(fileName, 'w+'))

from AccessGrid.hosting.pyGlobus.Utilities import GetDefaultIdentityDN

def HaveValidProxy():
    """
    This method determines whether a valid proxy exists
    """
    if GetDefaultIdentityDN() == None:
        return 0
    return 1

def formatExceptionInfo(maxTBlevel=5):
    cla, exc, trbk = sys.exc_info()
    excName = cla.__name__
    try:
        excArgs = exc.__dict__["args"]
    except KeyError:
        excArgs = "<no args>"
    excTb = traceback.format_tb(trbk, maxTBlevel)
    return (excName, excArgs, excTb)

def GetRandInt(r):
    return int(r.random() * sys.maxint)
    
def AllocateEncryptionKey():
    """
    This function returns a key that can be used to encrypt/decrypt media
    streams.    
    
    Return: string
    """
    
    # I know that the python documentation says the builtin random is not
    # cryptographically safe, but 1) our requirements are not fort knox, and 2)
    # the random function is being upgraded to a better version in Python 2.3
        
    rg = Random(time.time())
    
    intKey = GetRandInt(rg)
    
    for i in range(1, 8):
        intKey = intKey ^ rg.randrange(1, sys.maxint)

#    print "Key: %x" % intKey
    
    return "%x" % intKey

def GetResourceList( resourceFile ):
    """
    This method reads a file generated by vic and a tcl script
    (courtesy Bob Olson) which contains a vic-compatible description
    of video capture devices on the local machine.  
    Note:  the name of the file is hardcoded
    Note:  for now, the file should be generated at installation, and the
            user should be provided with instructions for generating the 
            file by hand.
           later, users should be able to force generation of the file
            from within the AG software

    An example of the file is as follows:

        device: o100vc.dll - Osprey Capture Card 2
        portnames:  external-in 
        device: Microsoft WDM Image Capture (Win32)
        portnames:  external-in 
        device: o100vc.dll - Osprey Capture Card 1
        portnames:  external-in 

    """
    from AccessGrid.Types import Capability, AGVideoResource
    import fileinput
    import re

    resources = []

    oDeviceMatch = re.compile("^device: (.*)")
    oPortnameMatch = re.compile("^portnames:  (.*[^\s])")

    print "resource file = ", resourceFile

    device = None
    portnames = None
    if os.path.exists(resourceFile):
        for line in fileinput.input(files = [resourceFile ] ):
            match = oDeviceMatch.match(line)
            if match != None:
                device = match.groups()[0]
            match = oPortnameMatch.match(line)
            if match != None:
                portnames = string.split( match.groups()[0], ' '  )

                # assume that, if we have portnames, we already have a device
                resources.append( AGVideoResource( Capability.VIDEO, device,
                                                   Capability.PRODUCER, portnames ) )
    else:
        print "Video resources file not found; run device discovery script"

    return resources

def SubmitBug():
    url = "http://bugzilla.mcs.anl.gov/accessgrid/post_bug.cgi"
    args = {}

    bugzilla_login = 'client-ui-bugzilla-user@mcs.anl.gov'
    bugzilla_password = '8977f68349f93fead279e5d4cdf9c3a3'

    args['Bugzilla_login'] = bugzilla_login
    args['Bugzilla_password'] = bugzilla_password
    args['product'] = "Virtual Venues Client Software"
    args['version'] = "2.0"
    args['component'] = "Client UI"
    args['rep_platform'] = "Other"
    
    #
    # This detection can get beefed up a lot; I say
    # NT because I can't tell if it's 2000 or XP and better
    # to not assume there.
    #
    # cf http://www.lemburg.com/files/python/platform.py
    #
    
    if sys.platform.startswith("linux"):
        args['op_sys'] = "Linux"
    elif sys.platform == "win32":
        args['op_sys'] = "Windows NT"
    else:
        args['op_sys'] = "other"
        
        args['priority'] = "P2"
        args['bug_severity'] = "normal"
        args['bug_status'] = "NEW"
        args['assigned_to'] = ""
        args['cc'] = "olson@mcs.anl.gov"   # email to be cc'd
        args['bug_file_loc'] = "http://"
        
        
        args['submit'] = "    Commit    "
        args['form_name'] = "enter_bug"
        
        # Bug information goes here
        args['short_desc'] = "Crash in Client UI"
        args['comment']="Here goes the backtrace"
        
        #
        # Now submit to the form.
        #
        
        params = urllib.urlencode(args)
        
        f = urllib.urlopen(url, params)
        
        #
        # And read the output.
        #
        
        out = f.read()
        f.close()
        
        print "Submit returns ", out
        
        o = open("out.html", "w")
        o.write(out)
        o.close()
#
# We use this import to get a reliable hostname; should be made more
# general later (in the event we are using something other than hosting.pyGlobus
#

try:
    import AccessGrid.hosting.pyGlobus.Utilities
    GetHostname = AccessGrid.hosting.pyGlobus.Utilities.GetHostname
except ImportError:
    import socket
    GetHostname = socket.getfqdn()

def InitMimeTypes(file):
    """
    This function is used to load in our AG specific mimetypes.
    """
    # This only works for augmenting the mailcap entries on Linux
    if os.path.isfile(file):
        success = mtm.ReadMailcap(file, 1)

    # For windows we have cope with the fact that it's the registry
    # that's dealt with during the "creating new associations" sequence
    # for now we load the mailcap file and stuff things in the registry
    if sys.platform == 'win32':
        fp = open(file)
        caps = mailcap.readmailcapfile(fp)
        fp.close()

        ftl = []
        for k in caps.keys():
            opencmd = u""
            printcmd = u""
            desc = u""
            ext = None
            cmds = []
            stuff = caps[k][0]
            for k2 in stuff.keys():
                if k2 == 'view':
                    cmds.append(('open', stuff[k2].replace('%s', '%1'), ''))
                elif k2 == 'description':
                    desc = stuff[k2]
                elif k2 == 'nametemplate':
                    ext = "." + stuff[k2].split('.')[1]
                elif k2 == 'print':
                    cmds.append((k2, stuff[k2].replace('%s', '%1'), ''))

            fileType = k.split('/')[1]
            fileType.replace('-', '.')
            Win32RegisterMimeType(k, ext, fileType, desc, cmds)
                    
    return success
    
def SetMimeTypeAssociation(mimetype, ext=None, desc=None, cmds=None):
    """
    This function registers information with the local machines mime types
    database so it can be retrieved later.
    """
    defaultFile = os.path.join(GetUserConfigDir(), "mailcap")
    file = open(defaultFile, 'a')

    if cmds.has_key('print'):
        printcmd = cmds['print']
    else:
        printcmd = ""
    if cmds.has_key('open'):
        opencmd = cmds['open']
    else:
        opencmd = ""
    
    line = "%s; " % mimetype

    # if there's not even an open command, bail
    if opencmd == "":
        return
    else:
        line += "%s; " % opencmd
    if printcmd != "":
        line += "%s; " % printcmd
    if desc != None:
        line += "description=%s; " % desc
    if ext != None:
        line += "nametemplate=%%s%s" % ext

    file.write(line)
    
def GetMimeCommands(filename = None, type = None, ext = None):
    """
    This function returns anything in the local mime type database for the
    type or extension specified.
    """
    cdict = dict()
    
    if type != None:
        fileType = mtm.GetFileTypeFromMimeType(type)
    elif ext != None:
        fileType = mtm.GetFileTypeFromExtension(ext)

    if fileType != None and filename != None:
        mimeType = fileType.GetMimeType()
        cmds = fileType.GetAllCommands(filename, mimeType)
        verbs, cmdlines = cmds
        for i in range(0, len(verbs)):
            cdict[string.lower(verbs[i])] = cmdlines[i]
    else:
        cdict = None

    return cdict
