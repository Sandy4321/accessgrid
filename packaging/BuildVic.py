#!/usr/bin/python
#
#  Build Vic
#

import os
import sys

SOURCE=sys.argv[1]
DEST=sys.argv[2]

VICDIR = os.path.join(SOURCE,'mmedia')


def build_win(dir):
    p = os.path.join(dir, "vic", "vic.2003.sln")
    os.system('devenv %s /rebuild "DDraw Release"' % (p,))
    
def build_linux(dir):
    os.chdir(dir)
    os.system('./vic-build')

def build_darwin(dir):
    os.chdir(dir)
    os.system('./vic-build')

def build_freebsd(dir):
    os.chdir(dir)
    os.system('./vic-build-freebsd')


# Set plat-specific bits
if sys.platform == 'win32':
    VIC_EXE = os.path.join(VICDIR,'vic','ddraw_release','vic.exe')
    copyExe = 'copy'
    build = build_win
elif sys.platform == 'linux2':
    VIC_EXE = os.path.join(VICDIR,'vic','vic')
    copyExe = 'cp -p'
    build = build_linux
elif sys.platform == 'darwin':
    VIC_EXE = os.path.join(VICDIR,'vic','vic')
    copyExe = 'cp -p'
    build = build_darwin
elif sys.platform == 'freebsd5' or sys.platform == 'freebsd6':
    VIC_EXE = os.path.join(VICDIR,'vic','vic')
    copyExe = 'cp'
    build = build_freebsd
else:
    raise Exception, 'Unsupported platform: ' + sys.platform
    
# Build if necessary
if not os.path.exists(VIC_EXE):
    build(VICDIR)

if os.path.exists(VIC_EXE):
    copyCmd = "%s %s %s" % (copyExe, VIC_EXE, DEST)
    os.system(copyCmd)
else:
    print '** Error : %s does not exist; not copying' % (VIC_EXE,)


