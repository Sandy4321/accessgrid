#-----------------------------------------------------------------------------
# Name:        CRSClient.py
# Purpose:     Certificate Request Service Client code.
# Created:     2002/12/12
# RCS-ID:      $Id: CRSClient.py,v 1.9 2006-03-15 21:35:22 turam Exp $
# Copyright:   (c) 2002
# Licence:     See COPYING.TXT
#-----------------------------------------------------------------------------


__revision__ = "$Id: CRSClient.py,v 1.9 2006-03-15 21:35:22 turam Exp $"

import xmlrpclib
from AccessGrid import Log
from AccessGrid.UrllibTransport import UrllibTransport

log = Log.GetLogger(Log.CRSClient)

class CRSClientInvalidURL(Exception):
    pass

class CRSClientConnectionFailed(Exception):
    pass

class CRSClient:
    def __init__(self, url, proxyHost = None, proxyPort = None):
        self.url = url
        log.debug('create client')

        if self.url is not None:

            if proxyHost is not None:
                if proxyPort is None:
                    proxyURL = "http://%s" % (proxyHost)
                else:
                    proxyURL = "http://%s:%s" % (proxyHost, proxyPort)

                transport = UrllibTransport(proxyURL)
            else:
                transport = None
                
            self.proxy = xmlrpclib.ServerProxy(url, transport = transport, verbose = 1)
        else:
            raise CRSClientInvalidURL

    def RequestCertificate(self, emailAddress, certReq):
        """
        Request a certificate from this service.
        
        @param emailAddress: the email address of the submitter
        @type emailAddress: string
        @param certReq: is the PEM-formatted certificate request.
        @type certReq: string containing PEM data

        @raise IOError: if the proxy fails for some reason
        @raise StandardError if the xmlrpc part fails
        @return: a unique token used to retrieve the certificate when
        it's ready.
        """

        log.debug("request certificate")
        try:
            token = self.proxy.RequestCertificate(emailAddress, certReq)
        except IOError:
            log.exception("IOError on Proxy.RequestCertificate")
            raise CRSClientConnectionFailed
        except StandardError, v:
            log.exception("Exception on xmlrpc RequestCertificate call")
            raise v

        #
        # this should also remove the token from the directory so
        # we don't have to request status for this cert again
        #

        return token

    def RetrieveCertificate(self, token):
        """
        Retrieve an issued certificate from this service.

        @param token: the token used to know the requestor should get a specific certificate.
        @type token: string

        @raise CRSClientConnectionFailed: if the service can't get the certificate.
        @raise StandardError: if the retrieve fails
        @return: tuple (status, value). If status is zero, value contains
        an error message about the failure. Otherwise, value is a string
        containing the certificate.
        """

        log.debug("retrieve certificate for token %s", token)

        try:
            certificate = self.proxy.RetrieveCertificate(token)
        except IOError:
            log.exception("IOError on Proxy.RetrieveCertificate")
            raise CRSClientConnectionFailed
        except StandardError, v:
            log.exception("error on proxy.RetrieveCertificate(%s)", token)
            raise v

        log.debug("retrieved certificate %s", certificate)
        return certificate

    def RetrieveCACertificates(self):
        """
        Retrieve the CA certificate(s) for this server.

        @raise CRSClientConnectionFailed: if the service can't get the certificate.
        @raise StandardError: if the retrieve fails
        @return: tuple (status, value). If status is zero, value contains
        an error message about the failure. Otherwise, value is a list of pairs
        (CACert, SigningPolicy) containing the CA certs and signing policy files
        comprising the certifiation path for the certs issued by this server.
        """

        try:
            rval = self.proxy.RetrieveCACertificates()
        except IOError:
            log.exception("IOError on Proxy.RetrieveCACertificates")
            raise CRSClientConnectionFailed
        except StandardError, v:
            log.exception("error on proxy.RetrieveCACertificates(%s)", token)
            raise v

        log.debug("retrieved certificate list %s", rval)
        return rval


if __name__ == "__main__":
    req = """-----BEGIN CERTIFICATE REQUEST-----\nMIIB0TCCAToCADBgMRQwEgYDVQQKEwtBY2Nlc3MgR3JpZDEdMBsGA1UECxMUYWdk\nZXYtY2EubWNzLmFubC5nb3YxEjAQBgNVBAsTCW15LmRvbWFpbjEVMBMGA1UEAxMM\nUm9iZXJ0IE9sc29uMIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC5lvEXiR5R\na6QOJJpRpOXz4R0DxnTVBOvTKvPijSmcc6IbNnNimS7oE/4U+IJtQblOGGdqRwLX\nHOmVY3nDQ60yhQ34ynME3Sr3ntAp6zFp5Ek7LgjOWyEP3hIVWh0Paa36FHn6nCvm\nDYz/1/Ns9c17zK/fWy+PYKMz8Vz0cs2O1wIDAQABoDIwMAYJKoZIhvcNAQkOMSMw\nITARBglghkgBhvhCAQEEBAMCBPAwDAYDVR0TAQH/BAIwADANBgkqhkiG9w0BAQQF\nAAOBgQB5HQyPLAR7XaD6S3Rsso/Q9cbPSxHeWJE4ehF5Ohp+0yAuBpc3L7/LlDkX\nvHri5JGXrGzJGf0/cqzzduh0S/ejMGksNiupsSPlHzkVhQNtAvD6A9OT+25wMyHI\nzSidh+6OJkSBLVb2tkEK5wd844MLE+m0lgTKbNX2C9UAZmfkKw==\n-----END CERTIFICATE REQUEST-----\n"""
    email = "olson+catext@mcs.anl.gov"

    token = "412d8f4d766c6290bd3acc7e74763b72"

    import os

    w, r = os.popen4("openssl req -noout -text")
    w.write(req)
    w.close()
    print r.read()

    submitServerURL = "http://www.mcs.anl.gov/fl/research/accessgrid/ca/agdev/server.cgi"
    print "Sending..."
    #certificateClient = CRSClient(submitServerURL)
    certificateClient = CRSClient(submitServerURL, "yips.mcs.anl.gov", 3128)
    #requestId = certificateClient.RequestCertificate(email, req)
    #print "Sent, got id ", requestId

    ret = certificateClient.RetrieveCertificate(token)
    print "got ret ", ret
