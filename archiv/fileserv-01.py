#!/usr/bin/env python

import os, sys, shutil, getopt, urllib, BaseHTTPServer, SimpleHTTPServer

maxdownloads = 1
cpid = -1

class FileServHTTPRequestHandler (BaseHTTPServer.BaseHTTPRequestHandler):
   server_version = "Simons FileServer"
   protocol_version = "HTTP/1.0"

   filename = "."
   location = "/"

   def log_request (self, code='-', size='-'):
      if code == 200:
         BaseHTTPServer.BaseHTTPRequestHandler.log_request (self, code, size)


   def do_GET (self):
      global maxdownloads, cpid

      # Redirect any request to the filename of the file to serve.
      # This hands over the filename to the client.

      if self.path != self.location:
         txt = """\
                <html>
                   <head><title>302 Found</title></head>
                   <body>302 Found <a href="%s">here</a>.</body>
                </html>\n""" % self.location
         self.send_response (302)
         self.send_header ("Location", self.location)
         self.send_header ("Content-type", "text/html")
         self.send_header ("Content-Length", str (len (txt)))
         self.end_headers ()
         self.wfile.write (txt)
         return

      maxdownloads -= 1

      # let a separate process handle the actual download, so that
      # multiple downloads can happen simultaneously.

      cpid = os.fork ()
      if cpid == 0:
         # Child process
         f = open (self.filename)
         size = os.path.getsize (self.filename)

         self.send_response (200)
         self.send_header ("Content-type", "application/octet-stream")
         self.send_header ("Content-Length", size)
         self.end_headers ()
         shutil.copyfileobj (f, self.wfile)
         f.close ()



class ForkingDownloadHTTPRequestHandler (SimpleHTTPServer.SimpleHTTPRequestHandler):
   def guess_type (self, path):
      return self.extensions_map['']

   def do_GET (self):
      global cpid

      cpid = os.fork ()
      if cpid == 0:
         # Child process
         SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET (self)



def usage (errmsg = None):
   if errmsg:
      print >>sys.stderr, errmsg
   print >>sys.stderr, "Usage:", sys.argv[0], "[-p <port>] [-c <count>] [file]"
   sys.exit (1)

if __name__=='__main__':
   port = 8080
   serve_file = True
   location = "/"

   try:
      options, filenames = getopt.getopt (sys.argv[1:], "c:p:")
   except getopt.GetoptError, desc:
      usage (desc)

   if len (filenames) == 1:
      filename = os.path.abspath (filenames[0])
      location = "/" + urllib.quote (os.path.basename (filename))
   else:
      usage ("Can only serve single files/directories.")

   if not os.path.exists (filename):
      usage ("%s: No such file or directory" % filenames[0])

   if os.path.isfile (filename):
      serve_file = True
   elif os.path.isdir (filename):
      serve_file = False
   else:
      usage ("%s: Neither file nor directory" % filenames[0])

   if serve_file:
      try:
         # Check for readability
         os.path.getsize (filename)
         open (filename).close ()
      except (OSError, IOError):
         usage ("%s: Not readable" % filenames[0])

   for option, val in options:
      if option == '-c':
         if not serve_file:
            print >>sys.stderr, "WARNING: Download count ignored for directories."
         try:
            maxdownloads = int (val)
         except ValueError:
            usage ("invalid download count: %r. Please specify an integer." % val)

      if option == '-p':
         try:
            port = int (val)
         except ValueError:
            usage ("invalid port number: %r. Please specify an integer" % value)
      else:
         usage ("Unknown option: %r" % option)

   # Directories sollten eigentlich als .tar.gz geliefert werden.
   # tempfile.mkstemp()

   if serve_file:
      # We have to somehow push the filename of the file to serve to the
      # class handling the requests. This is an evil way to do this...

      FileServHTTPRequestHandler.filename = filename
      FileServHTTPRequestHandler.location = location

      httpd = BaseHTTPServer.HTTPServer (('', port),
                                         FileServHTTPRequestHandler)
      while cpid != 0 and maxdownloads > 0:
         httpd.handle_request ()

   else:
      httpd = BaseHTTPServer.HTTPServer (('', port),
                                         ForkingDownloadHTTPRequestHandler)
      while cpid != 0:
         httpd.handle_request ()




   # wait for child processes to terminate

   if cpid != 0:
      try:
         while 1:
            os.wait ()
      except OSError:
         pass
