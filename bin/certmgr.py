#!/usr/bin/python
#-----------------------------------------------------------------------------
# Name:        certmgr.py
# Purpose:     Command line certificate management tool.
# Created:     9/10/2003
# RCS-ID:      $Id: certmgr.py,v 1.16 2007-01-12 21:10:00 turam Exp $
# Copyright:   (c) 2002
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
This tool is used on the command line to interact with the users certificate
environment.
"""
__revision__ = "$Id: certmgr.py,v 1.16 2007-01-12 21:10:00 turam Exp $"
__docformat__ = "restructuredtext en"

import string
import re
import shutil
import os
import os.path
import sys
import cmd

from optparse import Option

from AccessGrid.Toolkit import CmdlineApplication
from AccessGrid.Security import CertificateManager
from AccessGrid.Platform.Config import SystemConfig

class CertMgrCmdProcessor(cmd.Cmd):
    """
    The certificate manager is a command processor based application; this is
    the cmd derived class for processing input.
    """
    def __init__(self, certMgr, log):
        """
        The constructor for the cert mgr command processor.
        """
        cmd.Cmd.__init__(self)

        self.log = log
        self.certMgr = certMgr
        self.certMgrUI = CmdlineApplication.instance().GetCertificateManagerUI()
        self.certRepo = certMgr.GetCertificateRepository()
        self.interactive = 1
        self.forceOverwrite = 0

        self.setIdentityMode()
        
        self.certs = []

    def setInteractive(self, interactive):
        self.interactive = interactive

    def setForceOverwrite(self, force):
        self.forceOverwrite = force
        

    def setIdentityMode(self):
        """
        Method to set the tool into Identity mode.
        """
        self.mode = "identity"
        self.loadCerts()
        self.setPrompt()

    def setCAMode(self):
        """
        Method to set the tool into CA mode.
        """
        self.mode = "trustedCA"
        self.loadCerts()
        self.setPrompt()

    def setPrompt(self):
        """
        Set the prompt according to the current mode.
        """

        if self.mode == "identity":
            self.prompt = "(ID mode) > "
        else:
            self.prompt = "(CA mode) > "


    def inIdentityMode(self):
        """
        Method to check if the processor is in identity mode.
        """
        return self.mode == "identity"

    def loadCerts(self):
        """
        Method to load certificates from the specified location.
        """
        pred = lambda c: \
            c.GetMetadata("AG.CertificateManager.certType") == self.mode
        self.certs = list(self.certRepo.FindCertificates(pred))

    def emptyline(self):
        """
        Method to process empty lines.
        """
        pass

    def do_id(self, arg):
        """
        Usage:

        id

        Change to identity certificate manipulation mode.
        """
        self.setIdentityMode()

    def do_ca(self, arg):
        """
        Usage:

        ca

        Change to CA certificate manipulation mode.
        """
        self.setCAMode()

    def do_EOF(self, arg):
        """
        EOF processor.
        """
        return 1

    def do_quit(self, arg):
        """
        Usage:

        quit

        Quit the certificate manager.
        """
        return 1

    def do_list(self, line):
        """
        Usage:

        list

        List the available certificates.
        """

        self.loadCerts()

        for i in range(len(self.certs)):
            cert = self.certs[i]
            if self.certMgr.IsDefaultIdentityCert(cert):
                dstr = "(Default) "
            else:
                dstr = ""

            print "%d. %s%s" % (i + 1, dstr, str(cert.GetSubject()))

    def do_show(self, line):
        """
        Usage:

        show <certnum>

        Show detailed information about certificate <certnum>.
        """
        args = split_quoted(line)
        if len(args) != 1:
            print "Usage: show <certnum>"
            return 0

        num = self.getCertNum(args[0])
        if num is None:
            print "Invalid certificate number %s" % (args[0])
            return 0

        cert = self.certs[num]

        print "Subject: ", cert.GetSubject()
        print "Issuer: ", cert.GetIssuer()

        print self.certs[num].GetVerboseText()

    def do_delete(self, line):
        """
        Usage:

        delete <certnum>

        Delete certificate <certnum>.
        """
        args = split_quoted(line)
        if len(args) != 1:
            print "Usage: delete <certnum>"
            return 0

        num = self.getCertNum(args[0])
        if num is None:
            print "Invalid certificate number %s" % (args[0])
            return 0

        cert = self.certs[num]

        if self.interactive:

            print "Delete certificate %s? (y/n) " % (cert.GetSubject()),
            line = sys.stdin.readline()
            line = line.strip().lower()
            if line[0] != 'y':
                return 0

        isDefault = self.certMgr.IsDefaultIdentityCert(cert)

        self.certMgr.GetCertificateRepository().RemoveCertificate(cert)

        #
        # We've deleted our default identity; arbitrarily assign a new one.
        # User can pick a different one if he wants.
        #

        if isDefault:
            idCerts = self.certMgr.GetIdentityCerts()
            if len(idCerts) > 0:
                self.certMgr.SetDefaultIdentity(idCerts[0])
                self.certMgrUI.InitGlobusEnvironment()
        self.loadCerts()

# Disabled for 3.0, which does not use proxy certificates
#     def do_gen_proxy(self, line):
#         """
#         Usage:
#         gen_proxy
# 
#         Create a proxy from the default certificate.
#         """
#         self.certMgr.CreateProxy()
# 
#     def do_check_proxy(self, line):
#         """
#         Usage:
#         check_proxy
# 
#         Check to see if there is a valid proxy.
#         """
#         try:
#             proxy = self.certMgr.GetGlobusProxyCert()
#         except Exception:
#             proxy = None
# 
#         if proxy is None:
#             print "No proxy found."
#         else:
#             print "Proxy will expire: %s" % proxy.GetNotValidAfterText()
        
    def do_export(self, line):
        """
        Usage: export <num> <certfile> [<keyfile>]

        If <keyfile> is not specified, and the certificate has
        a private key, it will be included in <certfile>
        """

        args = split_quoted(line)
        if len(args) != 2 and len(args) != 3:
            print "Usage: export <num> <certfile> [<keyfile>]"
            return 0

        num = self.getCertNum(args[0])
        if num is None:
            print "Invalid certificate number ", args[0]
            return 0

        certFile = args[1]
        if len(args) == 3:
            keyFile = args[2]
        else:
            keyFile = None

        cert = self.certs[num]
        print "Export certificate %s to %s" % (cert.GetSubject(), certFile)

        if os.path.isdir(certFile):
            print "%s is a directory, cannot export" % (certFile)
            return 0

        if os.path.exists(certFile):
            if self.interactive:
                print "%s already exists, overwrite? " % (certFile),
                line = sys.stdin.readline()
                line = line.strip().lower()
                if line[0] != 'y':
                    return 0
            elif not self.forceOverwrite:
                print "Not writing: %s already exists" % (certFile)
                return 0

        if keyFile is not None:
            if os.path.isdir(keyFile):
                print "%s is a directory, cannot export" % (keyFile)
                return 0

            if os.path.exists(keyFile):
                if self.interactive:
                    print "%s already exists, overwrite? " % (keyFile),
                    line = sys.stdin.readline()
                    line = line.strip().lower()
                    if line[0] != 'y':
                        return 0
                elif not self.forceOverwrite:
                    print "Not writing: %s already exists" % (keyFile)
                    return 0

        #
        # We've validated that either the output files do not exist,
        # or that they exist and we can write to them.
        #

        #
        # Export.
        #

        if self.inIdentityMode():
            self.exportIdentityCert(cert, certFile, keyFile)
        else:
            self.exportCACert(cert, certFile)

    def exportIdentityCert(self, cert, certFile, keyFile):
        """
        This method exports an identity certificate.
        """
        try:
            fh = open(certFile, "w")
            fh.write(cert.cert.cert.as_pem())
            if keyFile is not None:
                fh.close()

                fh = open(keyFile, "w")

            #
            # We'll just copy the private key file, so we don't
            # have to deal with passphrases.
            #

            kpath = cert.GetKeyPath()
            kfh = open(kpath, "r")

            shutil.copyfileobj(kfh, fh)

            kfh.close()
            fh.close()
        except Exception, e:
            print "Export failed: ", e

    def exportCACert(self, cert, certFile):
        """
        This method exports a CA certificate from the users environment.
        """
        try:
            fh = open(certFile, "w")
            fh.write(cert.cert.cert.as_pem())
            fh.close()
        except Exception, e:
            print "Export failed: ", e

    def do_default(self, line):
        """
        Usage:

        default <certnum>

        Set certificate <certnum> to be the default identity certificate.
        """

        if not self.inIdentityMode():
            print "Must be in identity mode to set default certficate."
            return 0

        args = split_quoted(line)
        if len(args) != 1:
            print "Usage: default <certnum>"
            return 0

        num = self.getCertNum(args[0])
        if num is None:
            print "Invalid certificate number %s" % (args[0])
            return 0

        cert = self.certs[num]

        self.certMgr.SetDefaultIdentity(cert)

        print "Set %s to default" % (cert.GetSubject())

        self.loadCerts()

    def do_request_service(self, line):
        """
        Usage:

        request_service <servicename> <email>

        Generate and submit a certificate request for <servicename> on
        this host. <email> is the confirmation email address.
        
        """
        args = split_quoted(line)
        if len(args) != 2:
            print "Usage: request_service <servicename> <email>"
            return 0

        serviceName, email = args

        host = SystemConfig.instance().GetHostname()

        reqInfo = CertificateManager.ServiceCertificateRequestInfo(serviceName,
                                                                    host,
                                                                    email)

        self.certMgrUI.RequestCertificate(reqInfo, None, 0, None, None)
        
    def help_import(self):
        """
        Help message for the import command.
        """
        if self.inIdentityMode():
            print """
Usage:

        import <certfile> [<keyfile>]

If <keyfile> is not specified, and an identity
cert is being imported, the key must be included
in <certfile>.
"""
        else:
            print """
Usage:

        import <certfile> [<signing_policy_file>]

If <signing_policy_file> is not present, it is assumed to be
the base name of certfile, with a .signing_policy suffix.
"""

    def do_import(self, line):
        """
        This is a wrapper method for the command processor. Depending
        on what mode we are in (identity or ca) we'll import a certificate
        of that type into the users  environment.
        """
        if self.inIdentityMode():
            self.importIdentityCert(line)
        else:
            self.importCACert(line)

        self.loadCerts()

    def importIdentityCert(self, line):
        """
        This method imports an identity certificate into the users environment.
        """
        args = split_quoted(line)
        if len(args) != 1 and len(args) != 2:
            print "Usage: import <certfile> [<keyfile>]"
            return 0

        certFile = args[0]
        if len(args) == 2:
            keyFile = args[1]
        else:
            keyFile = None

        if not os.path.isfile(certFile):
            print "Certificate file %s does not exist" % (certFile)
            return 0

        if keyFile is not None and not os.path.isfile(keyFile):
            print "Key file %s does not exist" % (certFile)
            return 0

        certRE = re.compile("-----BEGIN CERTIFICATE-----")
        keyRE = re.compile("-----BEGIN RSA PRIVATE KEY-----")

        try:
            fh = open(certFile)

            validCert = validKey = 0

            for line in fh:
                if not validCert and certRE.search(line):
                    validCert = 1
                    if validKey:
                        break
                if not validKey and keyRE.search(line):
                    validKey = 1
                    keyFile = certFile
                    if validCert:
                        break
            fh.close()
            self.log.debug("scan complete, validKey=%s validCert=%s", validKey,
                                                                 validCert)

        except IOError:
            print "Could not open certificate file %s", (certFile)
            return None

        except:
            print "Unexpected error opening certificate file %s" % (certFile)
            return None

        #
        # Test to see if we had a valid PEM-formatted certificate.
        #

        if not validCert:
            print "Certificate file %s doesn't appear to contain a PEM-encode \
            certificate" % (certFile)
            return 0

        #
        # We've got our cert. See if we need to open the keyfile as well.
        #

        if validKey:
            #
            # There was a key in the cert file.
            #

            if keyFile is not None:
                print "Private key found in certificate file %s; ignoring key \
                file %s" %(certFile, keyFile)
                keyFile = certFile

        elif keyFile is None:
            print "Private key not found in certificate file %s and no key \
            file specified; cannot import" %(certFile)
            return None

        try:
            ui = self.certMgrUI
            cb = ui.GetPassphraseCallback("Private key passphrase",
                                "Enter the passphrase to your private key.")
            impCert = self.certMgr.ImportIdentityCertificatePEM(self.certMgr.GetCertificateRepository(),
                                                                certFile, keyFile, cb)
            print "Imported identity %s" % ( str(impCert.GetSubject()))
            self.loadCerts()

        except Exception, e:
            print "Error importing certificate from %s keyfile %s: %s" % (certFile, keyFile, e)
            return 0

        #
        # Check to see if we have the CA cert for the issuer of this cert.
        #

        if not self.certMgr.VerifyCertificatePath(impCert):
            print "Cannot verify the certificate path for \n" + \
                  str(impCert.GetSubject()) + "\n" \
                  "This certificate may not be usable until the \n" + \
                  "appropriate CA certificates are imported. At the least,\n" + \
                  "the certificate for this CA must be imported:\n" + \
                  str(impCert.GetIssuer()) + "\n" + \
                  "It might be found in a file %s.0." % (impCert.GetIssuer().get_hash())

        #
        # Check to see if there is a default identity cert. If not, make
        # this the default.
        #

        idCerts = self.certMgr.GetDefaultIdentityCerts()

        print "Got id certs: ", idCerts
        self.do_list("")
        if len(idCerts) == 0:
            self.certMgr.SetDefaultIdentity(impCert)

        return impCert


    def importCACert(self, line):
        """
        This method imports a CA cert into the users environment.
        """
        args = split_quoted(line)
        if len(args) != 1 and len(args) != 2:
            print "Usage: import <certfile> [<signing_policy>]"
            return 0

        certFile = args[0]
        if len(args) == 2:
            spFile = args[1]
        else:
            base, ext = os.path.splitext(certFile)
            spFile = base + ".signing_policy"

        if not os.path.isfile(certFile):
            print "Certificate file %s does not exist" % (certFile)
            return 0

        if not os.path.isfile(spFile):
            print "Signing policy file %s does not exist" % (spFile)
            return 0

        certRE = re.compile("-----BEGIN CERTIFICATE-----")

        try:
            fh = open(certFile)

            validCert = 0

            for line in fh:
                if certRE.search(line):
                    validCert = 1
                    break
            fh.close()
            self.log.debug("scan complete, validCert=%s",  validCert)

        except IOError:
            print "Could not open certificate file %s", (certFile)
            return None

        except:
            print "Unexpected error opening certificate file %s" % (certFile)
            return None

        #
        # Test to see if we had a valid PEM-formatted certificate.
        #

        if not validCert:
            print "Certificate file %s doesn't appear to contain a PEM-encode certificate" % (certFile)
            return 0

        try:
            impCert = self.certMgr.ImportCACertificatePEM(self.certMgr.GetCertificateRepository(),
                                                          certFile)
            print "Imported CA certificate %s" % ( str(impCert.GetSubject()))

            shutil.copyfile(spFile, impCert.GetFilePath("signing_policy"))

        except Exception, e:
            print "Error importing certificate from %s: %s" % (certFile, e)
            return 0

        return impCert

    def getCertNum(self, a):
        """
        Validate 'a' as a certificate number, and return it if valid.
        Return None if invalid.

        If 'a' is not an integer, attempt to match a certificate's DN with
        it. If it matches, return the number of the matching cert.
        """


        if re.search(r"^\d+$", a):

            num = int(a)
            num -= 1

            if num < 0 or num >= len(self.certs):
                return None

            return num
        
        else:

            num = 0;
            for c in self.certs:
                if str(c.GetSubject()) == a:
                    return num
                num += 1
            return None


#
# split_quoted borrowed from distutils.
#
# We're using it without the backslash escaping enabled
# so that we can use it for windows pathnames.
#


# Needed by 'split_quoted()'
_wordchars_re = re.compile(r'[^\'\"%s ]*' % string.whitespace)
_squote_re = re.compile(r"'(?:[^'\\]|\\.)*'")
_dquote_re = re.compile(r'"(?:[^"\\]|\\.)*"')

def split_quoted (s):
    """Split a string up according to Unix shell-like rules for quotes and
    backslashes.  In short: words are delimited by spaces, as long as those
    spaces are not escaped by a backslash, or inside a quoted string.
    Single and double quotes are equivalent, and the quote characters can
    be backslash-escaped.  The backslash is stripped from any two-character
    escape sequence, leaving only the escaped character.  The quote
    characters are stripped from any quoted string.  Returns a list of
    words.
    """

    # This is a nice algorithm for splitting up a single string, since it
    # doesn't require character-by-character examination.  It was a little
    # bit of a brain-bender to get it working right, though...

    s = string.strip(s)
    words = []
    pos = 0

    while s:
        m = _wordchars_re.match(s, pos)
        end = m.end()
        if end == len(s):
            words.append(s[:end])
            break

        if s[end] in string.whitespace: # unescaped, unquoted whitespace: now
            words.append(s[:end])       # we definitely have a word delimiter
            s = string.lstrip(s[end:])
            pos = 0

        else:
            if s[end] == "'":           # slurp singly-quoted string
                m = _squote_re.match(s, end)
            elif s[end] == '"':         # slurp doubly-quoted string
                m = _dquote_re.match(s, end)
            else:
                raise RuntimeError, \
                      "this can't happen (bad char '%c')" % s[end]

            if m is None:
                raise ValueError, \
                      "bad string (mismatched %s quotes?)" % s[end]

            (beg, end) = m.span()
            s = s[:beg] + s[beg+1:end-1] + s[end:]
            pos = m.end() - 2

        if pos >= len(s):
            words.append(s)
            break

    return words

# split_quoted ()

def main():
    """
    The main routine.
    """
    # Instantiate the app
    app = CmdlineApplication()

    caOption = Option("-C", "--ca", action = "store_true",
                      dest = "is_ca_mode", default = 0,
                      help = "Use CA mode for this invocation of the certificate manager.")
    idOption = Option("-I", "--id", action = "store_false",
                      dest = "is_ca_mode", default = 0,
                      help = "Use ID mode for this invocation of the certificate manager.")

    forceOption = Option("-f", "--force", action = "store_true",
                         dest = "force_overwrite", default = 0,
                         help = "Overwrite existing files.")
    app.AddCmdLineOption(caOption)
    app.AddCmdLineOption(idOption)
    app.AddCmdLineOption(forceOption)

    try:
        args = app.Initialize("CertificateManager")
    except Exception:
        sys.exit(0)

    cmd = CertMgrCmdProcessor(app.GetCertificateManager(), app.GetLog())

    #
    # If no args were passed, start up the command-driver
    # cert mgr.
    #

    if app.GetOption("is_ca_mode"):
        cmd.setCAMode()

    if len(args) == 0:
        
        cmd.cmdloop()

    else:

        #
        # Otherwise, process a single command from teh command line.
        #

        cmd.setInteractive(0)
        cmd.setForceOverwrite(app.GetOption("force_overwrite"))

        mycmd = args[0] + " " + " ".join(map(lambda a: '"' + a + '"', args[1:]))
        print mycmd
        cmd.onecmd(mycmd)


if __name__ == "__main__":
    main()
