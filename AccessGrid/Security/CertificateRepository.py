#-----------------------------------------------------------------------------
# Name:        CertificateRepository.py
# Purpose:     Cert management code.
# Created:     2003
# RCS-ID:      $Id: CertificateRepository.py,v 1.24 2006-10-13 21:29:52 turam Exp $
# Copyright:   (c) 2002
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------
"""
Certificate management module.

The on-disk repository looks like this:

<repo_root>/
            metadata.db
            certificates/<subject_hash>/
                               <issuer_serial_hash>/cert.pem
                                                    user_files/
                               <modulus_hash>.req.pem
            privatekeys/
                        <modulus_hash>


"""

__revision__ = "$Id: CertificateRepository.py,v 1.24 2006-10-13 21:29:52 turam Exp $"

from __future__ import generators

import re
import sys
import os
import os.path
import time
import string
import md5
import struct
import weakref

from AccessGrid.Platform import IsOSX

if IsOSX():
    import bsddb185 as bsddb
else:
    import bsddb

import operator
import cStringIO
from AccessGrid import Log
from AccessGrid import Utilities
from AccessGrid.Security import ProxyGen

log = Log.GetLogger(Log.CertificateRepository)

from M2Crypto import X509
from M2Crypto import RSA
from M2Crypto import EVP
from M2Crypto import m2

class RepoAlreadyExists(Exception):
    """
    Thrown if repository already exists, and the CertificateRepository
    constructor was invoked with create=1.
    """
    pass

class RepoDoesNotExist(Exception):
    """
    Thrown if repository does not exist, and the CertificateRepository
    constructor was invoked with create=0.
    """
    pass

class RepoInvalidCertificate(Exception):
    """
    Thrown if an attempt was made to use an invalid certificate.
    """
    pass

class RepoBadPassphrase(Exception):
    pass

def ClassifyCertificate(path):
    """
    Prod at the certificate given to see what it is,
    and if we need to ask for a private key.
    
    A PEM-formatted cert will have a "BEGIN CERTIFICATE"
    line; if it has a private key included it'll include
    "BEGIN RSA PRIVATE KEY".
    
    If it's unencrypted, we'll get the actual certificate, and can
    show the name.
    
    We return a tuple (certType, certObj, needPkey). CertType is a string
    "PEM", "PKCS12". certObj is the certificate itself; it'll be an X509
    for a PEM certificate, a PKCS12 object for a pkcs12 obj. needPkey is
    true if a separate keyfile must be loaded.
    """

    certRE = re.compile("-----BEGIN CERTIFICATE-----")
    keyRE = re.compile("-----BEGIN RSA PRIVATE KEY-----")

    try:
        fh = open(path)

        validCert = validKey = 0

        for l in fh:
            if not validCert and certRE.search(l):
                validCert = 1
                if validKey:
                    break
            if not validKey and keyRE.search(l):
                validKey = 1
                if validCert:
                    break
        fh.close()

    except IOError:
        log.error("Could not open certificate file %s", path)
        return None
    
    if validCert:
        log.info("Found valid cert, validKey=%s", validKey)
        c = X509.load_cert(path)
        return ("PEM", c, not validKey)

    return None

def ParseSigningPolicy(policyFH):
    """
    Parse a signing policy from filehandle policyFH.

    For now, we just return the CA name that it represents so we don't
    get bogged down in parsing minutiae.
    """

    for l in policyFH:
        l = l.strip()
        if l.startswith("#"):
            continue

        if l == "":
            continue;

        key, v1, v2 = l.split(None, 2)

        if key == "access_id_CA":
            if v1 != "X509":
                return None
            ca = v2
            if ca[0] == "'":
                ca = eval(ca)


            return ca
    return None

def ConstructSigningPolicy(cert):
    """
    Construct a simple signing policy based on the subject name of cert.

    It might not be right, but it might be.

    We make it match on all parts of the cert's subject except for CN.
    """

    caName = str(cert.GetSubject())

    subjs = filter(lambda a: a[0] != "CN", cert.GetSubject().get_name_components())
    subjs = [cert.GetSubject().CN]

    condSubjects = "/".join(map(lambda a: a[0] + "=" + a[1], subjs))

    sp = """
#
# Signing policy automatically generated.
#
 access_id_CA       X509      '%(caName)s'
 pos_rights         globus    CA:sign
 cond_subjects      globus    '"/%(condSubjects)s/*"'
""" % locals()

    return sp

class CertificateRepository:

    #
    # Private key types.
    #

    KEYTYPE_RSA = "RSA"

    #
    # Valid name components for cert request DNs. Lowercased
    # for easy comparison.
    #

    validNameComponents = [
        "cn",
        "c",
        "l",
        "st",
        "o",
        "ou",
        "emailaddress"
        ]
    
    def __init__(self, repoDir, create = 0):
        """
        Create the repository.

        @param repoDir: directory in which to store certificates.
        @param create: true if we should create the repository

        """

        self.dir = repoDir
        self.dbPath = os.path.join(self.dir, "metadata.db")
        self.metadataLocked = 0

        #
        # We maintain a list of observers that may be interested in
        # updates to the state of the repo (certificates deleted or imported).
        #

        self.observers = []

        if create:
            if os.path.isdir(self.dir):
                raise RepoAlreadyExists
            os.makedirs(self.dir)
            os.mkdir(os.path.join(self.dir, "user_files"))
            os.mkdir(os.path.join(self.dir, "privatekeys"))
            os.mkdir(os.path.join(self.dir, "requests"))
            os.mkdir(os.path.join(self.dir, "certificates"))
            # Create the dbhash too.
            self.db = bsddb.hashopen(self.dbPath, 'n')
            self.db.sync()
        else:
            # Just check for directory existence now; we can/should
            # add more checks that the repo dir actually does contain
            # a valid repository.
            if not os.path.isdir(self.dir):
                raise RepoDoesNotExist

            # Look for other stuff too
            invalidRepo = 0

            for mustExist in ('user_files', 'privatekeys', 'requests',
                              'certificates'):
                if not os.path.isdir(os.path.join(self.dir, mustExist)):
                    invalidRepo = 1

            if not os.path.isfile(self.dbPath):
                invalidRepo = 1

            try:
                self.db = bsddb.hashopen(self.dbPath, 'w')
                self.db.sync()
                
            except bsddb.error:

                invalidRepo = 1
                
                log.exception("exception opening hash %s", self.dbPath)

                try:
                    self.db.close()
                except:
                    pass

                # See if this might be an old-style DB hash (pre-python2.3)
                if sys.version[:3] >= "2.3":
                    try:
                        import bsddb185
                            
                        self.db = bsddb185.hashopen(self.dbPath, 'w')
                        #
                        # It worked.
                        #
                        invalidRepo = 0
                        log.info("Fallback to bsddb 1.85 succeeded for %s", self.dbPath)
                        
                    except ImportError:
                        log.error("bsddb185 module not available in this python install, marking certRepo as corrupt")
                    except bsddb.error:
                        log.exception("attempted fallback to 1.85 bsddb failed")
                
                #
                # Try to figure out what's going on. Stat the db and
                # its directory and log the information.
                #
                if invalidRepo:
                    try:
                        xx = os.stat(self.dbPath)
                        pred = lambda x: x.startswith("st_")
                        log.error("Stats on %s:", self.dbPath)
                        for k in filter(pred, dir(xx)):
                            log.error("%s: %s", k, getattr(xx, k))

                        xx = os.stat(self.dir)
                        log.error("Stats on %s:", self.dir)
                        for k in filter(pred, dir(xx)):
                            log.error("%s: %s", k, getattr(xx, k))
                    except:
                        log.exception("error trying to read stats")

            if invalidRepo:
                #
                # The repository index is corrupted somehow.
                #

                #
                # Attempt to recover from the files making up the repo.
                #

                try:
                    recovered = self.RecoverFromDirectory()
                except:
                    log.exception("Recovery failed")
                    recovered = 0

                if recovered:
                    #
                    # Whee, that worked.
                    #

                    return
                
                #
                # Rename it, log an error, and raise an exception.
                #

                #
                # Close an opened db, otherwise the rename will fail due
                # to the open file.
                #
                try:
                    self.db.close()
                except:
                    pass
                
                newname = "%s.corrupt.%s" % (self.dir, int(time.time()))
                try:
                    os.rename(self.dir, newname)
                    log.error("Detected corrupted repository, renaming to %s", newname)
                    raise RepoDoesNotExist
                except OSError:
                    log.exception("Error in attempt to move aside corrupted repository")
                    
                    raise Exception("Cannot open repository, and cannot initialize new repository")

    def RecoverFromDirectory(self):
        """
        Attempt to recover a repository index from the flat-files
        in the repository.
        """

        #
        # First check that the directory appears to be a repository.
        #

        log.info("Recovering repository from %s", self.dir)
        if not os.path.isdir(self.dir):
            log.info("Recovery failed: %s is not a directory", self.dir)
            return 0

        for f in ("user_files", "privatekeys", "requests", "certificates"):
            p = os.path.join(self.dir, f)
            if not os.path.isdir(p):
                log.info("Recovery failed: %s is not a directory", p)
                return 0

        #
        # Looks like a repo.
        #
        # We'll create a new empty db.
        #

        if os.path.isfile(self.dbPath):
            #
            # If there's one there, move it out of the way. (but only if we
            # (haven't done it yet).
            #

            backup = self.dbPath + ".before_recovery"

            if not os.path.isfile(backup):
                try:
                    os.rename(self.dbPath, backup)

                except:
                    log.exception("rename from %s to %s failed", self.dbPath, backup)
                    return 0
        try:
            self.db = bsddb.hashopen(self.dbPath, 'n')
            self.db.sync()

        except:
            #
            # We couldn't create a new one. Abort the recovery attempt.
            #
            log.exception("Cannot open new dbhash file %s", self.dbPath)
            return 0
            

        #
        # First scan the privatekeys.
        #

        privatekeys = {}
        for f in os.listdir(os.path.join(self.dir, "privatekeys")):
            m = re.match("(.*).pem", f)
            if m:
                p = os.path.join(self.dir, "privatekeys", f)
                # Ugh. m.group(1) is returning unicode, and forcing more stuff
                # later to unicode, and breaking the bsddb.
                mhash = str(m.group(1))
                privatekeys[mhash] = p
                log.info("Found private key %s", mhash)
                self.RecoverPrivateKey(mhash, p)

        #
        # Now scan the certificates directory. Recall that this is organized
        # as subject-hash/issuer-serial-hash.
        #
        # We pass down a dictionary of recovery state information.
        #

        recoveryState = {'firstCert': 1,
                         'privatekeys': privatekeys,
                         }

        for subj_hash in os.listdir(os.path.join(self.dir, "certificates")):
            if not(len(subj_hash) == 32 and re.search("^[0-9a-f]*$", subj_hash)):
                continue

            log.info("Probing subject hash dir %s", subj_hash)
            subj_dir = os.path.join(self.dir, "certificates", subj_hash)

            for issuer_serial_hash in os.listdir(subj_dir):
                if not(len(subj_hash) == 32 and re.search("^[0-9a-f]*$", subj_hash)):
                    continue

                log.info("Have issuer-serial hash %s", issuer_serial_hash)

                cert_path = os.path.join(subj_dir, issuer_serial_hash, "cert.pem")
                if os.path.isfile(cert_path):
                    log.info("Have certificate %s", cert_path)

                    self.RecoverCert(cert_path, recoveryState)

        return 1

    def RecoverPrivateKey(self, hash, path):
        """
        Recover privatekey information for the repo db.
        """

        #
        # Try to load it to see if it's encrypted.
        #

        try:
            keyText = open(path).read()
            RSA.load_key(path)

            # Not encrypted
            self.SetPrivatekeyMetadata(hash, "System.encrypted", "0")

        except:# crypto.Error:
            # Encrypted.
            self.SetPrivatekeyMetadata(hash, "System.encrypted", "1")

# turam: determine exceptions that can be raised by RSA.load_key,
#       at least in these two cases
#         except IOError:
# 
#             log.info("Couldn't open private key file %s", path)
#             

    def RecoverCert(self, path, recoveryState):
        """
        Recover certificate information for the repo db.

        @param path: pathname ot the certificate being recovered
        @param recoverState: dictionary used for maintaining state between
        calls to RecoverCert.
        """
        
        try:
            cert = Certificate(path, repo = self)

        except:

            log.exception("error loading certificate from %s", path)
            return

        log.info("Recovering certificate %s", str(cert.GetSubject()))

        cert.SetMetadata("System.importTime", str(time.time()))
        cert.SetMetadata("System.certImportedFrom", path)

        #
        # See if there is a private key.
        #

        mhash = cert.GetModulusHash()
        pkeyPath = self.GetPrivateKeyPath(mhash)

        if recoveryState['privatekeys'].has_key(mhash):

            pkeyPath = recoveryState['privatekeys'][mhash]

            log.info("Private key found for certificate at %s", pkeyPath)
        
            cert.SetMetadata("System.keyImportedFrom", pkeyPath)
            cert.SetMetadata("System.hasKey", "1")

            #
            # This means it's an identity cert.
            #
            # We're breaking a boundary here, setting an AG.CertificateManager
            # value. That's okay for now.
            #

            cert.SetMetadata("AG.CertificateManager.certType", "identity")

            #
            # We can't tell which one should be default, so we pick the first
            # we see.
            #

            if recoveryState['firstCert']:
                log.info("Setting cert as default")
                cert.SetMetadata("AG.CertificateManager.isDefaultIdentity", "1")
                recoveryState['firstCert'] = 0
            else:
                cert.SetMetadata("AG.CertificateManager.isDefaultIdentity", "0")

            
        else:
            cert.SetMetadata("System.hasKey", "0")

            #
            # Call certs without keys trustedCA certs.
            #

            cert.SetMetadata("AG.CertificateManager.certType", "trustedCA")


    def RegisterObserver(self, observer):
        """
        Register an observer with the cert repo.

        @param observer: a callable object which will be invoked
        with a single argument, a handle to this repo.

        """

        # Use a weakref so we don't unnecessarily hold
        # a reference to the observer.
        wr = weakref.ref(observer)

        if wr not in self.observers:
            self.observers.append(wr)

    def UnregisterObserver(self, observer):
        """
        Unregister an observer from the cert repo.

        @param observer: The observer to be removed.

        """

        wr = weakref.ref(observer)

        if wr in self.observers:
            self.observers.remove(wr)

    def NotifyObservers(self):
        """
        Send a notification to the observers.
        """
        
        removeList = []
        for obs in self.observers:
            obj = obs()
            if obj is None:
                #
                # Referent is gone, remove from list.
                #
                removeList.append(obs)
            else:
                try:
                    obj(self)
                except:
                    log.exception("Exception raised when calling observer %s", obj)
                    removeList.append(obs)

        for obs in removeList:
            self.observers.remove(obs)

    def LockMetadata(self):
        """
        Lock the metadata in the repo. If metadata is locked, any attempts
        to call SetMetadata will fail.
        """
    
        self.metadataLocked = 1
        
    def UnlockMetadata(self):
        """
        Unlock the metadata in the repo.
        """
    
        self.metadataLocked = 0

    def ImportCertificatePEM(self, certFile, keyFile = None,
                             passphraseCB = None):
        """
        Import a PEM-formatted certificate from certFile.

        If keyFile is not None, load it as a private key for cert.

        We don't currently inspect the key itself to ensure it matches
        the certificate, as that may require a passphrase.
        """

        # Load the cert into a pyOpenSSL data structure.
        cert = Certificate(certFile, keyFile, self)
        path = self._GetCertDirPath(cert)
        # print "Would put cert in dir ", path

        # If the path already exists, we already have this (uniquely named)
        # certificate.

        if os.path.isdir(path):
            raise RepoInvalidCertificate("Certificate already in repository.", path)

        #
        # Load the private key. This will require getting the
        # passphrase for the key. Do that here, so we can pass
        # that passphrase down to the importPrivateKey call
        # so it is imported with the same passphrase.
        #
        # We try to load the key without a passphrase first.
        #

        #print "pkey file is ", keyFile
        
        pkey = None
        if keyFile is not None:
            keyText = open(keyFile).read()

            #
            # We try to load the key without a passphrase first.
            #
            
            try:
                pkey = RSA.load_key(keyFile)

                #
                # Success.
                #

                passphrase = None

            except:# crypto.Error:

                #
                # We need a passphrase. Get one from the user,
                # and then try again.
                #

                if passphraseCB is None:
                    raise Exception, "This private key requires a passphrase"

                passphrase = passphraseCB(0)

                if passphrase is None:
                    raise RepoBadPassphrase
                
                if type(passphrase) == list:
                    #
                    # Convert from list-of-numbers to a string.
                    #
                    # Replace this when pyOpenSSL fixed to understand lists.
                    #

                    if type(passphrase[0]) == int:
                        passphrase = "".join(map(lambda a: chr(a), passphrase))
                    else:
                        passphrase = "".join(passphrase)

                try:
                    pkey = RSA.load_key(keyFile,passphraseCB)

# Determine exceptions that could be raised here and handle individually
                except:# crypto.Error:
                    log.exception("load error")
                    raise RepoBadPassphrase

            #
            # At this point pkey has is the privatekey.
            # Doublecheck that the pubkey modulus on the
            # certificate we're importing matches hte
            # modulus on this private key. Otherwise,
            # they're not a matching pair.
            #

            if pkey.get_modulus() != cert.GetModulus():
                raise Exception, "Private key does not match certificate"
            else:
                #print "Modulus match: ", pkey.get_modulus()
                pass

        # Preliminary checks successful. We can go ahead and import.
        #
        # Import the private key first, so that if we get an exception
        # on the passphrase we're not left with intermediate state.
        # (aie, transactions anyone?)
        if pkey is not None:
            self._ImportPrivateKey(pkey, passphrase)

        self._ImportCertificate(cert, path)

        # Import done, set the metadata about the cert.
        cert.SetMetadata("System.importTime", str(time.time()))
        cert.SetMetadata("System.certImportedFrom", certFile)
        if keyFile:
            cert.SetMetadata("System.keyImportedFrom", keyFile)
            cert.SetMetadata("System.hasKey", "1")
        else:
            cert.SetMetadata("System.hasKey", "0")

        return CertificateDescriptor(cert, self)
            
    def ImportCertificateX509(self, certobj, pkey = None,
                              passphraseCB = None):
        """
        Import a PEM-formatted certificate from OpenSSL X509
        data structure cert, optional PKey data structre in pkey.

        """

        # The certificate wrapper class we use in this module
        # requires that the certificate be loaded from a file.
        io = cStringIO.StringIO(certobj.as_pem())
        cert = Certificate(None, certHandle = io)
        io.close()

        path = self._GetCertDirPath(cert)
        # print "Would put cert in dir ", path

        # If the path already exists, we already have this (uniquely named)
        # certificate.
        if os.path.isdir(path):
            raise RepoInvalidCertificate, "Certificate already in repository at %s" % (path)

        # Load the private key. This will require getting the
        # passphrase for the key. Do that here, so we can pass
        # that passphrase down to the importPrivateKey call
        # so it is imported with the same passphrase.
        #
        # We try to load the key without a passphrase first.

        if pkey:
            # Doublecheck that the pubkey modulus on the
            # certificate we're importing matches hte
            # modulus on this private key. Otherwise,
            # they're not a matching pair.
            if pkey.get_modulus() != cert.GetModulus():
                raise Exception, "Private key does not match certificate"
            else:
                #print "Modulus match: ", pkey.get_modulus()
                pass

        # Preliminary checks successful. We can go ahead and import.
        #
        # Import the private key first, so that if we get an exception
        # on the passphrase we're not left with intermediate state.
        # (aie, transactions anyone?)

        if pkey is not None:
            passphrase = passphraseCB(0)
            self._ImportPrivateKey(pkey, passphrase)

        self._ImportCertificate(cert, path)

        #
        # Import done, set the metadata about the cert.
        #

        cert.SetMetadata("System.importTime", str(time.time()))
        cert.SetMetadata("System.certImportedFrom", certFile)
        cert.SetMetadata("System.hasKey", "0")

        return CertificateDescriptor(cert, self)
            
    def ImportRequestedCertificate(self, certFile, passphraseCB = None):
        """
        Import a certificate that we earlier issued a request for.
        """

        # Load the cert into a pyOpenSSL data structure.
        cert = Certificate(certFile, repo = self)
        path = self._GetCertDirPath(cert)

        # If the path already exists, we already have this (uniquely named)
        # certificate.
        if os.path.isdir(path):
            raise RepoInvalidCertificate, "Certificate already in repository at %s" % (path)

        # Check to see that we have a private key already for this cert.
        mhash = cert.GetModulusHash()
        pkeyPath = self.GetPrivateKeyPath(mhash)

        if not os.path.isfile(pkeyPath):
            log.error("we don't have a private key for this certificate")
            raise RepoInvalidCertificate("No private key exists for this certificate")

        # Preliminary checks successful. We can go ahead and import.
        self._ImportCertificate(cert, path)

        # Import done, set the metadata about the cert.
        cert.SetMetadata("System.importTime", str(time.time()))
        cert.SetMetadata("System.certImportedFrom", certFile)
        cert.SetMetadata("System.hasKey", "1")

        return CertificateDescriptor(cert, self)
            
    def _ImportCertificate(self, cert, path):
        """
        Import a certificate. We've already done the due diligence
        that this is a valid cert that is okay to just copy into place.
        """

        os.makedirs(path)

        certPath = os.path.join(path, "cert.pem")
        cert.WriteCertificate(certPath)
        
        # Set permissions on the certificate as needed by unix globus
        # (globus requires it for service certificates, but it's a good
        #  idea generally)
        os.chmod(certPath, 0644)

    def _ImportCertificateRequest(self, req):
        """
        Import the given certificate request into the repository.

        req is an M2Crypto.X509.Request object.

        The pathname of the imported request will be
        <repo_root>/requests/<modulus_hash>.pem.
        """

        desc = CertificateRequestDescriptor(req, self)

        mhash = desc.GetModulusHash()

        path = os.path.join(self.dir,
                            "requests",
                            "%s.pem" % (mhash))

        log.info("_ImportCertificateRequest writing to %s", path)
        fh = open(path, 'w')
        fh.write(req.as_pem())
        fh.close()

        return desc

    def GetPrivateKeyPath(self, hash):
        path = os.path.join(self.dir,
                            "privatekeys",
                            "%s.pem" % (hash))
        return path

    def _ImportPrivateKey(self, pkey, passwdCB):
        """
        Import the given private key into the repository.

        passwdCB is passed to the underlying pyOpenSSL routine if it is
        present and not None. It can be either a string, in which case
        it represents the passphrase, or a python callable object, in which
        case it will be invoked by the underlying pyOpenSSL code to
        retrieve the desired passphrase.
        """

        #
        # Compute the directory to store the key in based on a
        # md5 hash of the key's public-key modulus.
        #

        dig = md5.new(pkey.get_modulus())
        hhash = dig.hexdigest()

        path = self.GetPrivateKeyPath(hhash)
        
        log.info("_ImportPrivateKey importing pkey to %s", path)

        # If passwdCB is none, don't encrypt.
        if passwdCB is None:
            # Retrieve PEM representation of certificate
            # (NULL cipher specifies unencrypted private key)
            pktext = pkey.as_pem(cipher=None)
            self.SetPrivatekeyMetadata(hhash, "System.encrypted", "0")

        else:
            if type(passwdCB) == str:
                passwdCB = lambda verify,prompt1="",prompt2="",passwd=passwdCB: passwd
            pktext = pkey.as_pem(callback = passwdCB)
            self.SetPrivatekeyMetadata(hhash, "System.encrypted", "1")
            
        fh = open(path, 'w')
        fh.write(pktext)
        fh.close()
        #
        # Make the private key unreadable. Necessary for Unix-based Globus.
        #
        os.chmod(path, 0400)

    def _GetCertDirPath(self, cert):
        """
        Compute the path name for the directory the cert will use
        """

        path = os.path.join(self.dir,
                            "certificates",
                            cert.GetSubjectHash(),
                            cert.GetIssuerSerialHash())
        return path

    def RemoveCertificate(self, cert, retainPrivateKey = 0):
        """
        Remove the specificed certificate from the repository.
        """

        #
        # Determine the certificate path.
        #

        if isinstance(cert, CertificateDescriptor):
            cert = cert.cert

        certDir = self._GetCertDirPath(cert)
        if not os.path.isdir(certDir):
            log.warn("RemoveCertificate: Cannot find path %s", certDir)
            return

        try:
            Utilities.removeall(certDir)
            os.rmdir(certDir)
        except:
            log.exception("Error removing cert directories at %s", certDir)

        #
        # Remove stuff from the metadata database.
        #

        metaPrefix = "|".join(["certificate",
                               cert.GetSubjectHash(),
                               cert.GetIssuerSerialHash()])
        pkeyMetaPrefix = "|".join(["privatekey",
                                   cert.GetModulusHash()])
        try:
            for key in self.db.keys():
                if key.startswith(metaPrefix):
                    del self.db[key]
                    log.info("RemoveCertificate deleting key %s", key)
                if key.startswith(pkeyMetaPrefix):
                    del self.db[key]
                    log.info("RemoveCertificate deleting key %s", key)
        finally:
            self.db.sync()

        #
        # Remove any private keys.
        #

        if not retainPrivateKey:

            pkeyfile = os.path.join(self.dir,
                                    "privatekeys",
                                    "%s.pem" % (cert.GetModulusHash()))

            if not os.path.isfile(pkeyfile):
                log.warn("No private key dir found at %s", pkeyfile)
            else:
                try:
                    # Need to chmod it writable before we can remove.
                    os.chmod(pkeyfile, 0600)
                    os.remove(pkeyfile)
                except:
                    log.exception("Error removing private key directory at %s", pkeyfile)
        
        self.NotifyObservers()
    #
    # Certificate Request support
    #

    def CreateCertificateRequest(self, nameEntries, passphraseCB,
                                 keyType = KEYTYPE_RSA,
                                 bits = 1024,
                                 messageDigest = "md5",
                                 extensions = None):
        """
        Create a new certificate request and store it in the repository.
        Returns a CertificateRequestDescriptor for that request.

        nameEntries is a list of pairs (key, value) where key is
        a standard distinguished name key, and value is the value to
        be used for that key.

        extensions is a list of triples (name, critical, value) to be used
        to set the requests extensions. If passed in as none, a useful
        default set of extensions will be used.
        """

        #
        # make sure nameEntries is what we expect it to be.
        #

        if not operator.isSequenceType(nameEntries):
            raise Exception, "nameEntries must be a sequence"

        try:
            for k, v in nameEntries:
                if k.lower() not in self.validNameComponents:
                    raise Exception, "Invalid name component %s" % (k)
        except ValueError:
            raise Exception, "Invalid value in nameEntry list"
        except TypeError:
            raise Exception, "nameEntries may not be a list"

        #
        # Name list is okay. Create the cert request obj and set up the
        # subject.
        #

        req = X509.Request()
        sub = req.get_subject()
        for (k,v) in nameEntries:
            setattr(sub,k,v)

        #
        # set our extensions.
        #
        
        if extensions is None:
            extensions = [("nsCertType", 0, "client,server,objsign,email"),
                          ("basicConstraints", 1, "CA:false")
                          ]
        extStack = X509.X509_Extension_Stack()
        for name, critical, value in extensions:
            xext = X509.new_extension(name,value,critical)
            extStack.push(xext)
        req.add_extensions(extStack)

        #
        # Generate our private key, stash it in the repo,
        # and sign the cert request.
        #

        pkey = EVP.PKey()
        rsa = RSA.gen_key(bits,65537)
        pkey.assign_rsa(rsa)
        req.set_pubkey(pkey)
        req.sign(pkey,messageDigest)

        self._ImportPrivateKey(pkey,passphraseCB)
        desc = self._ImportCertificateRequest(req)
        return desc
        
    def RemoveCertificateRequest(self, req):
        """
        Remove the specificed certificate request from the repository.
        """

        mhash = req.GetModulusHash()

        path = os.path.join(self.dir, "requests", "%s.pem" % (mhash))

        try:
            os.unlink(path)
        except:
            log.exception("error removing certificate file %s", path)

        #
        # Remove any metadata.
        #

        metaPrefix = "|".join(["request", mhash])

        try:
            for key in self.db.keys():
                if key.startswith(metaPrefix):
                    del self.db[key]
                    log.info("RemoveCertificateRequest deleting key %s", key)
        finally:
            self.db.sync()

    #
    # Certificate database querying methods
    #
    
        
    def _GetCertificates(self):
        """
        This is a generator function that will walk through all of the
        certificates we have.
        """

        certDir = os.path.join(self.dir, "certificates")

        if not os.path.isdir(certDir):
            log.error("Certificate Repository error: %s is not a directory",
                      certDir)
            return
        
        subjHashes = os.listdir(certDir)
        for subjHash in subjHashes:
            subjHashDir = os.path.join(certDir, subjHash)

            if not os.path.isdir(subjHashDir):
                log.info("Found a non-directory %s in cert dir %s",
                         subjHash, certDir)
                continue
            
            isHashes = os.listdir(subjHashDir)
            for isHash in isHashes:

                isHashDir = os.path.join(subjHashDir, isHash)
                if not os.path.isdir(isHashDir):
                    log.info("Found a non-directory %s in subject hash dir %s",
                             isHash, subjHashDir)
                    continue
                
                certFile = os.path.join(isHashDir, "cert.pem")

                if os.path.isfile(certFile):
                    desc = CertificateDescriptor(Certificate(certFile, repo = self), self)
                    yield desc
                else:
                    log.info("Expected to find a cert.pem at %s, but did not",
                             isHashDir)

    def _GetCertificateRequests(self):
        """
        This is a generator function that will walk through all of the
        certificates we have.
        """

        reqDir = os.path.join(self.dir, "requests")
        files = os.listdir(reqDir)

        reqRE = re.compile("^.*\.pem$")
        files = filter(reqRE.search, files)
        for fileN in files:
            path = os.path.join(reqDir, fileN)
            if os.path.isfile(path):

                try:
                    req = X509.load_request(path)
                    desc = CertificateRequestDescriptor(req, self)
                    yield desc

                except:
                    log.exception("Error loading certificate request %s", path)

    def GetAllCertificates(self):
        return self._GetCertificates()

    def FindCertificates(self, pred):
        """
        Return a list of certificates for which pred(cert) returns true.
        """

        #
        # This is also a generator. That way, we can short-circuit the
        # search if we only want some.
        #

        for cert in self._GetCertificates():
            if pred(cert):
                yield cert

    def FindCertificatesWithSubject(self, subj):
        return list(self.FindCertificates(lambda c: str(c.GetSubject()) == subj))
    
    def FindCertificatesWithIssuer(self, issuer):
        return list(self.FindCertificates(lambda c: str(c.GetIssuer()) == issuer))
    
    def FindCertificatesWithMetadata(self, mdkey, mdvalue):
        return list(self.FindCertificates(lambda c: c.GetMetadata(mdkey) == mdvalue))

    def GetAllCertificateRequests(self):
        return self._GetCertificateRequests()

    def FindCertificateRequests(self, pred):
        """
        Return a list of certificate requests for which pred(req) returns true.
        """

        #
        # This is also a generator. That way, we can short-circuit the
        # search if we only want some.
        #

        for cert in self._GetCertificateRequests():
            if pred(cert):
                yield cert

    def FindCertificateRequestsWithSubject(self, subj):
        return list(self.FindCertificateRequests(lambda c: str(c.GetSubject()) == subj))
    
    def FindCertificateRequestsWithMetadata(self, mdkey, mdvalue):
        return list(self.FindCertificateRequests(lambda c: c.GetMetadata(mdkey)  == mdvalue))
    
    def SetPrivatekeyMetadata(self, modulus, key, value):
        hashkey = "|".join(["privatekey",
                            modulus,
                            key])
        self.SetMetadata(hashkey, value)

    def GetPrivatekeyMetadata(self, modulus, key):
        hashkey = "|".join(["privatekey",
                            modulus,
                            key])
        return self.GetMetadata(hashkey)

    def SetMetadata(self, key, value):
        if self.metadataLocked:
            log.error("Attempting to set metadata on locked repository")
            return
        
        try:
            self.db[str(key)] = value
        finally:
            self.db.sync()
    
    def GetMetadata(self, key):
        key = str(key)
        if self.db.has_key(key):
            return self.db[key]
        else:
            return None

class CertificateDescriptor:
    def __init__(self, cert, repo):
        self.cert = cert
        self.repo = repo

    def GetPath(self):
        return self.cert.GetPath()

    def GetKeyPath(self):
        return self.cert.GetKeyPath()

    def GetIssuer(self):
        return self.cert.GetIssuer()

    def GetShortSubject(self):
        return self.cert.GetShortSubject()

    def GetSubject(self):
        return self.cert.GetSubject()

    def GetVersion(self):
        return self.cert.GetVersion()

    def GetSerialNumber(self):
        return self.cert.GetSerialNumber()

    def GetFingerprint(self):
        return self.cert.GetFingerprint()

    def GetMetadata(self, k):
        return self.cert.GetMetadata(k)

    def SetMetadata(self, k, v):
        return self.cert.SetMetadata(k, v)

    def GetFilePath(self, file):
        return self.cert.GetFilePath(file)

    def GetVerboseText(self):
        return self.cert.GetVerboseText()

    def GetVerboseHtml(self):
        return self.cert.GetVerboseHtml()

    def GetModulus(self):
        return self.cert.GetModulus()

    def GetModulusHash(self):
        return self.cert.GetModulusHash()

    def HasEncryptedPrivateKey(self):
        mod = self.GetModulusHash()
        isEncrypted = self.repo.GetPrivatekeyMetadata(mod, "System.encrypted")
        if isEncrypted == "1":
            return 1
        else:
            return 0
    def GetNotValidBefore(self):
        return self.cert.GetNotValidBefore()
    
    def GetNotValidAfter(self):
        return self.cert.GetNotValidAfter()

    def GetNotValidBeforeText(self):
        return self.cert.GetNotValidBeforeText()
    
    def GetNotValidAfterText(self):
        return self.cert.GetNotValidAfterText()

    def IsExpired(self):
        return self.cert.IsExpired()

    def IsServiceCert(self):
        return self.cert.IsServiceCert()

    def IsHostCert(self):
        return self.cert.IsHostCert()
        
    def IsProxyCert(self):
        return ProxyGen.IsProxyCert(self.cert)

class CertificateRequestDescriptor:
    def __init__(self, req, repo):
        self.req = req
        self.repo = repo
        self.modulusHash = None

    def GetSubject(self):
        return self.req.get_subject()

    def GetModulus(self):
        key = self.req.get_pubkey()
        return key.get_modulus()
        
    def GetModulusHash(self):
        if self.modulusHash is None:
            m = self.GetModulus()
            dig = md5.new(m)
            self.modulusHash = dig.hexdigest()
        return self.modulusHash

    def _GetMetadataKey(self, key):
        hashkey = "|".join(["request",
                            self.GetModulusHash(),
                            key])
        return hashkey

    def GetMetadata(self, key):
        return self.repo.GetMetadata(self._GetMetadataKey(key))

    def SetMetadata(self, key, value):
        return self.repo.SetMetadata(self._GetMetadataKey(key), value)

    def ExportPEM(self):
        """
        Returns the PEM-formatted version of the certificate request.
        """

        return self.req.as_pem()

class Certificate:
    hostCertRE = re.compile(r"^[^\s./]+(\.[^\s./]+)+$")
    serviceCertRE = re.compile(r"^([^/]*)/([^/]*)$")
    def __init__(self,  path, keyPath = None, repo = None, certHandle = None, certText = None):
        """
        Create a certificate object.

        This wraps an underlying OpenSSL X.509 cert object.

        @param path: pathname of the stored certificate.
        @param keyPath: pathname of the private key for the certificate
        @param repo: certificate repository to be used as a reference for lookup operations.
        @param certHandle: a file handle to use for loading the certificate. If this is specified,
        path must be None.
        @param certText: Actual text of the certificate. Again, if specified, path must be None.
        """

        self.path = path
        self.keyPath = keyPath
        self.repo = repo

        #
        # Cached hash values.
        #
        self.subjectHash = None
        self.issuerSerialHash = None
        self.modulusHash = None

        if certHandle is not None:
            if path is not None:
                log.error("Cannot specify both certHandle and path")

            self.certText = certHandle.read()
        elif certText is not None:
            self.certText = certText

        else:
            fh = open(self.path, "r")
            self.certText = fh.read()
            fh.close()

        self.cert = X509.load_cert(self.path)


        #
        # We don't load the privatekey with the load_privatekey method,
        # as that requires the passphrase for the key.
        # We'll just cache the text here.
        #

        if keyPath is not None:
            fh = open(keyPath, "r")
            self.keyText = fh.read()
            fh.close()
            
    def GetKeyPath(self):
        #
        # Key path is based on the modulus.
        #
        if self.keyPath is not None:
            return self.keyPath
        
        if not self.repo:
           return None

        if self.IsProxyCert():
            keypath = self.path
        else:
            keypath = os.path.join(self.repo.dir,
                            "privatekeys",
                            "%s.pem" % (self.GetModulusHash()))
                            
        return keypath

    def GetPath(self):
        return self.path

    def GetSubject(self):
        return self.cert.get_subject()

    def GetShortSubject(self):
        cn = [self.cert.get_subject().CN]
        return ", ".join(cn)

    def GetIssuer(self):
        return self.cert.get_issuer()

    def GetSubjectHash(self):

        if self.subjectHash is None:
            subj = self.cert.get_subject().as_der()
            dig = md5.new(subj)
            self.subjectHash = dig.hexdigest()

        return self.subjectHash

    def GetIssuerSerialHash(self):

        if self.issuerSerialHash is None:
            issuer = self.cert.get_issuer().as_der()
            #
            # Get serial number in its 4-byte form
            #
            serial = struct.pack("l", self.cert.get_serial_number())
            dig = md5.new(issuer)
            dig.update(serial)
            self.issuerSerialHash = dig.hexdigest()

        return self.issuerSerialHash

    def GetModulus(self):
        key = self.cert.get_pubkey()
        return key.get_modulus()
        
    def GetModulusHash(self):
        if self.modulusHash is None:
            m = self.GetModulus()
            dig = md5.new(m)
            self.modulusHash = dig.hexdigest()
        return self.modulusHash

    def IsExpired(self):
        return self.cert.is_expired()

    def IsServiceCert(self):
        """
        A service cert has a CN of the form servicename/hostname.

        @return: If a service cert, (servicename, hostname). Otherwise, None.

        """

        cnlist = self.GetSubject().CN
        if len(cnlist) != 1:
            return None

        m = self.serviceCertRE.search(cnlist[0])

        if m and len(m.groups()) == 2:
            return m.group(1), m.group(2)
        else:
            return None

    def IsHostCert(self):
        """
        A host cert has a CN of the form "hostname".

        @return: If a service cert, hostname. Otherwise, None.

        """

        #cnlist = map(lambda a: a[1], filter(lambda a: a[0] == "CN", self.GetSubject().get_name_components()))
        cnlist = self.GetSubject().CN
        if len(cnlist) != 1:
            return None


        m = self.hostCertRE.search(cnlist[0])

        if m:
            return cnlist[0]
        else:
            return None

    def IsProxyCert(self):
        return ProxyGen.IsProxyFile(self.path)

    def WriteCertificate(self, file):
        """
        Write the certificate to the given file.
        """

        fh = open(file, "w")
        fh.write(self.cert.as_pem())
        fh.close()

    def _GetMetadataKey(self, key):
        hashkey = "|".join(["certificate",
                            self.GetSubjectHash(),
                            self.GetIssuerSerialHash(),
                            key])
        return hashkey

    def GetFilePath(self, filename):
        dirN = os.path.join(self.repo._GetCertDirPath(self), "user_files")
        if not os.path.isdir(dirN):
            os.mkdir(dirN)
        return os.path.join(dirN, filename)

    def GetMetadata(self, key):
        hashkey = self._GetMetadataKey(key)
        val = self.repo.GetMetadata(hashkey)
        return val

    def SetMetadata(self, key, value):
        hashkey = self._GetMetadataKey(key)
        self.repo.SetMetadata(hashkey, value)

    def GetNotValidBefore(self):
        """
        Return notbefore time as seconds since the epoch
        """
        notBefore = str(self.cert.get_not_before())
        sec = utc2time(notBefore)
        return sec

    def GetNotValidAfter(self):
        """
        Return notafter time as seconds since the epoch
        """
        notAfter = self.cert.get_not_after()
        sec = utc2time(notAfter)
        return sec

    def GetNotValidBeforeText(self):
        """
        Return notbefore time as a text string in the local timezone.
        """
        notBefore = self.cert.get_not_before()
        sec = utc2time(notBefore)
        return time.strftime("%x %X", time.localtime(sec))

    def GetNotValidAfterText(self):
        """
        Return notafter time as a text string in the local timezone.
        """
        notAfter = self.cert.get_not_after()
        sec = utc2time(notAfter)
        return time.strftime("%x %X", time.localtime(sec))

    def GetVersion(self):
        # version is 0-based
        return self.cert.get_version() + 1

    def GetSerialNumber(self):
        return self.cert.get_serial_number()

    def GetFingerprint(self):
        """
        Returns a tuple (type, fingerprint)
        """
        
        ctype,fp = self.cert.get_fingerprint()
        return ctype, string.join(map(lambda a: "%02X" % (a), fp), ":")

    def GetVerboseText(self):
        fmt = ""
        
        cert = self.cert
        fmt += "Certificate version: %s\n" % (cert.get_version())
        fmt += "Serial number: %s\n" % (cert.get_serial_number())

        fmt += "Not valid before: %s\n" % (self.GetNotValidBeforeText())
        fmt += "Not valid after: %s\n" %  (self.GetNotValidAfterText())

        ctype,fp = self.GetFingerprint()
        fmt += "%s Fingerprint: %s\n"  % (ctype,
                                          string.join(map(lambda a: "%02X" % (a), fp), ":"))
        fmt += "Certificate location: %s\n" % (self.GetPath(),)
        
        pkeyloc = self.GetKeyPath()
        
        if os.access(pkeyloc, os.R_OK):
            fmt += "Private key location: %s\n" % (pkeyloc,)

        return fmt

    def GetVerboseHtml(self):
        fmt = ""
        
        cert = self.cert
        fmt += "<b>Subject:</b>: %s<br>\n" % (cert.get_subject())
        fmt += "<b>Issuer:</b>: %s<br>\n" % (cert.get_issuer())
        fmt += "<b>Certificate version</b>: %s<br>\n" % (cert.get_version())
        fmt += "<b>Serial number</b>: %s<br>\n" % (cert.get_serial_number())

        fmt += "<b>Not valid before:</b> %s<br>\n" % (self.GetNotValidBeforeText())
        fmt += "<b>Not valid after:</b> %s<br>\n" %  (self.GetNotValidAfterText())

        ctype,fp = self.GetFingerprint()
        fmt += "<b>%s Fingerprint:</b> %s<br>\n"  % (ctype,
                                          string.join(map(lambda a: "%02X" % (a), fp), ":"))
        fmt += "<b>Certificate location:</b> %s<br>\n" % (self.GetPath(),)
        pkeyloc = self.GetKeyPath()

        if os.access(pkeyloc, os.R_OK):
            fmt += "<b>Private key location:</b> %s<br>\n" % (pkeyloc,)

        return fmt
    
if __name__ == "__main__":

    certPath = os.path.join(os.environ["HOME"], ".globus", "usercert.pem")
    keyPath = os.path.join(os.environ["HOME"], ".globus", "userkey.pem")
    c = Certificate(certPath)

    print "hash = ", c.GetSubjectHash(), c.GetIssuerSerialHash()

    repo = CertificateRepository("repo", 1)
    print "Importing ", certPath

    try:
        repo.ImportCertificatePEM(certPath, keyPath)
    except RepoInvalidCertificate:
        print "Cert already there maybe"

    # Import some CA certs

    caDir = r"\Program Files\Windows Globus\certificates"
    for certFile in os.listdir(caDir):
        if re.search(r"\.\d+$", certFile):
            try:
                repo.ImportCertificatePEM(os.path.join(caDir, certFile))
            except RepoInvalidCertificate:
                print "yup, you can't import a proxy"
    
    certlist = list(repo._GetCertificates())
    print "Certs: "
    for c in certlist:
        print "%s %s" % (c.GetIssuer(), c.GetSubject())

    globus = "/C=US/O=Globus/CN=Globus Certification Authority"
    me = "/O=Grid/O=Globus/OU=mcs.anl.gov/CN=Bob Olson"
    print "My certs: ", repo.FindCertificatesWithSubject(me)
    print "Globus certs: ", repo.FindCertificatesWithIssuer(globus)

#
# YYMMDDHHMMSSZ
#

def utc2tuple(t):
    if len(t) == 13:
        year = int(t[0:2])
        if year >= 50:
            year = year + 1900
        else:
            year = year + 2000

        month = t[2:4]
        day = t[4:6]
        hour = t[6:8]
        minute = t[8:10]
        sec = t[10:12]
        zone = t[12]
        if zone != "Z":
            raise ValueError("utc2tuple received unknown timeformat (timezone != Z) " + t)
        
    elif len(t) == 15:
        year = int(t[0:4])
        month = t[4:6]
        day = t[6:8]
        hour = t[8:10]
        minute = t[10:12]
        sec = t[12:14]
        zone = t[14]
        if zone != "Z":
            raise ValueError("utc2tuple received unknown timeformat (timezone != Z): " + t)
    else:
        raise ValueError("utc2tuple received unknown timeformat (unknown length): " + t)
    
    ttuple = (year, int(month), int(day), int(hour), int(minute),
              int(sec), 0, 0, -1)
    return ttuple

def utc2time(t):
    """
    Convert a UTC time (as kept in the X509 notbefore/notafter fields)
    to seconds since the epoch.

    We need to handle conversion out of our local timezone, because
    time.mktime() converts to the local timezone, but the tuple returned
    by utc2tuple is GMT.
    """
    
    ttuple = time.strptime(str(t), "%b %d %H:%M:%S %Y %Z")
    secs = int(time.mktime(ttuple))
    #
    # Adjust for local timezone.
    #
    secs -= time.timezone
    return secs

