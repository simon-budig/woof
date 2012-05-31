#!/usr/bin/env python
# -*- encoding: utf-8 -*-
#
#  woof -- an ad-hoc single file webserver
#  Copyright (C) 2004-2009 Simon Budig  <simon@budig.de>
# 
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  A copy of the GNU General Public License is available at
#  http://www.fsf.org/licenses/gpl.txt, you can also write to the
#  Free Software  Foundation, Inc., 59 Temple Place - Suite 330,
#  Boston, MA 02111-1307, USA.

# Darwin support with the help from Mat Caughron, <mat@phpconsulting.com>
# Solaris support by Colin Marquardt, <colin.marquardt@zmd.de>
# FreeBSD support with the help from Andy Gimblett, <A.M.Gimblett@swansea.ac.uk>
# Cygwin support by Stefan Reichör <stefan@xsteve.at>
# tarfile usage suggested by Morgan Lefieux <comete@geekandfree.org>
# File upload support loosely based on code from Stephen English <steve@secomputing.co.uk>

import sys, os, errno, socket, getopt, commands, tempfile
import cgi, urllib, urlparse, BaseHTTPServer
import readline
import ConfigParser
import shutil, tarfile, zipfile
import struct

maxdownloads = 1
TM = object
cpid = -1
compressed = 'gz'
upload = False


class EvilZipStreamWrapper(TM):
   def __init__ (self, victim):
      self.victim_fd = victim
      self.position = 0
      self.tells = []
      self.in_file_data = 0

   def tell (self):
      self.tells.append (self.position)
      return self.position

   def seek (self, offset, whence = 0):
      if offset != 0:
         if offset == self.tells[0] + 14:
            # the zipfile module tries to fix up the file header.
            # write Data descriptor header instead,
            # the next write from zipfile
            # is CRC, compressed_size and file_size (as required)
            self.write ("PK\007\010")
         elif offset == self.tells[1]:
            # the zipfile module goes to the end of the file. The next
            # data written definitely is infrastructure (in_file_data = 0)
            self.tells = []
            self.in_file_data = 0
         else:
            raise "unexpected seek for EvilZipStreamWrapper"

   def write (self, data):
      # only test for headers if we know that we're not writing
      # (potentially compressed) data.
      if self.in_file_data == 0:
         if data[:4] == zipfile.stringFileHeader:
            # fix the file header for extra Data descriptor
            hdr = list (struct.unpack (zipfile.structFileHeader, data[:30]))
            hdr[3] |= (1 << 3)
            data = struct.pack (zipfile.structFileHeader, *hdr) + data[30:]
            self.in_file_data = 1
         elif data[:4] == zipfile.stringCentralDir:
            # fix the directory entry to match file header.
            hdr = list (struct.unpack (zipfile.structCentralDir, data[:46]))
            hdr[5] |= (1 << 3)
            data = struct.pack (zipfile.structCentralDir, *hdr) + data[46:]

      self.position += len (data)
      self.victim_fd.write (data)

   def __getattr__ (self, name):
      return getattr (self.victim_fd, name)


# Utility function to guess the IP (as a string) where the server can be
# reached from the outside. Quite nasty problem actually.

def find_ip ():
   # we get a UDP-socket for the TEST-networks reserved by IANA.
   # It is highly unlikely, that there is special routing used
   # for these networks, hence the socket later should give us
   # the ip address of the default route.
   # We're doing multiple tests, to guard against the computer being
   # part of a test installation.

   candidates = []
   for test_ip in ["192.0.2.0", "198.51.100.0", "203.0.113.0"]:
      s = socket.socket (socket.AF_INET, socket.SOCK_DGRAM)
      s.connect ((test_ip, 80))
      ip_addr = s.getsockname ()[0]
      s.close ()
      if ip_addr in candidates:
         return ip_addr
      candidates.append (ip_addr)

   return candidates[0]


# our own HTTP server class, fixing up a change in python 2.7
# since we do our fork() in the request handler
# the server must not shutdown() the socket.

class ForkingHTTPServer (BaseHTTPServer.HTTPServer):
   def process_request(self, request, client_address):
      self.finish_request (request, client_address)
      self.close_request (request)


# Main class implementing an HTTP-Requesthandler, that serves just a single
# file and redirects all other requests to this file (this passes the actual
# filename to the client).
# Currently it is impossible to serve different files with different
# instances of this class.

class FileServHTTPRequestHandler (BaseHTTPServer.BaseHTTPRequestHandler):
   server_version = "Simons FileServer"
   protocol_version = "HTTP/1.0"

   filename = "."

   def log_request (self, code='-', size='-'):
      if code == 200:
         BaseHTTPServer.BaseHTTPRequestHandler.log_request (self, code, size)


   def do_POST (self):
      global maxdownloads, upload

      if not upload:
         self.send_error (501, "Unsupported method (POST)")
         return
      
      # taken from
      # http://mail.python.org/pipermail/python-list/2006-September/402441.html

      ctype, pdict = cgi.parse_header (self.headers.getheader ('Content-Type'))
      form = cgi.FieldStorage (fp = self.rfile,
                               headers = self.headers,
                               environ = {'REQUEST_METHOD' : 'POST'},
                               keep_blank_values = 1,
                               strict_parsing = 1)
      if not form.has_key ("upfile"):
         self.send_error (403, "No upload provided")
         return
         
      upfile = form["upfile"]

      if not upfile.file or not upfile.filename:
         self.send_error (403, "No upload provided")
         return
      
      upfilename = upfile.filename

      if "\\" in upfilename:
         upfilename = upfilename.split ("\\")[-1]

      upfilename = os.path.basename (upfile.filename)

      destfile = None
      for suffix in ["", ".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9"]:
         destfilename = os.path.join (".", upfilename + suffix)
         try:
            destfile = os.open (destfilename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0644)
            break
         except OSError, e:
            if e.errno == errno.EEXIST:
               continue
            raise

      if not destfile:
         upfilename += "."
         destfile, destfilename = tempfile.mkstemp (prefix = upfilename, dir = ".")

      print >>sys.stderr, "accepting uploaded file: %s -> %s" % (upfilename, destfilename)

      shutil.copyfileobj (upfile.file, os.fdopen (destfile, "w"))
      
      if upfile.done == -1:
         self.send_error (408, "upload interrupted")

      txt = """\
              <html>
                <head><title>Woof Upload</title></head>
                <body>
                  <h1>Woof Upload complete</title></h1>
                  <p>Thanks a lot!</p>
                </body>
              </html>
            """
      self.send_response (200)
      self.send_header ("Content-Type", "text/html")
      self.send_header ("Content-Length", str (len (txt)))
      self.end_headers ()
      self.wfile.write (txt)

      maxdownloads -= 1

      return
      

   def do_GET (self):
      global maxdownloads, cpid, compressed, upload

      # Form for uploading a file
      if upload:
         txt = """\
                 <html>
                   <head><title>Woof Upload</title></head>
                   <body>
                     <h1>Woof Upload</title></h1>
                     <form name="upload" method="POST" enctype="multipart/form-data">
                       <p><input type="file" name="upfile" /></p>
                       <p><input type="submit" value="Upload!" /></p>
                     </form>
                   </body>
                 </html>
               """
         self.send_response (200)
         self.send_header ("Content-Type", "text/html")
         self.send_header ("Content-Length", str (len (txt)))
         self.end_headers ()
         self.wfile.write (txt)
         return

      # Redirect any request to the filename of the file to serve.
      # This hands over the filename to the client.

      self.path = urllib.quote (urllib.unquote (self.path))
      location = "/" + urllib.quote (os.path.basename (self.filename))
      if os.path.isdir (self.filename):
         if compressed == 'gz':
            location += ".tar.gz"
         elif compressed == 'bz2':
            location += ".tar.bz2"
         elif compressed == 'zip':
            location += ".zip"
         else:
            location += ".tar"

      if self.path != location:
         txt = """\
                <html>
                   <head><title>302 Found</title></head>
                   <body>302 Found <a href="%s">here</a>.</body>
                </html>\n""" % location
         self.send_response (302)
         self.send_header ("Location", location)
         self.send_header ("Content-Type", "text/html")
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
         child = None
         type = None
         
         if os.path.isfile (self.filename):
            type = "file"
         elif os.path.isdir (self.filename):
            type = "dir"

         if not type:
            print >> sys.stderr, "can only serve files or directories. Aborting."
            sys.exit (1)

         self.send_response (200)
         self.send_header ("Content-Type", "application/octet-stream")
         self.send_header ("Content-Disposition", "attachment;filename=%s" % urllib.quote (os.path.basename (self.filename)))
         if os.path.isfile (self.filename):
            self.send_header ("Content-Length",
                              os.path.getsize (self.filename))
         self.end_headers ()

         try:
            if type == "file":
               datafile = file (self.filename)
               shutil.copyfileobj (datafile, self.wfile)
               datafile.close ()
            elif type == "dir":
               if compressed == 'zip':
                  ezfile = EvilZipStreamWrapper (self.wfile)
                  zfile = zipfile.ZipFile (ezfile, 'w', zipfile.ZIP_DEFLATED)
                  stripoff = os.path.dirname (self.filename) + os.sep

                  for root, dirs, files in os.walk (self.filename):
                     for f in files:
                        filename = os.path.join (root, f)
                        if filename[:len (stripoff)] != stripoff:
                           raise RuntimeException, "invalid filename assumptions, please report!"
                        zfile.write (filename, filename[len (stripoff):])
                  zfile.close ()
               else:
                  tfile = tarfile.open (mode=('w|' + compressed),
                                        fileobj=self.wfile)
                  tfile.add (self.filename,
                             arcname=os.path.basename (self.filename))
                  tfile.close ()
         except Exception, e:
            print e
            print >>sys.stderr, "Connection broke. Aborting"


def serve_files (filename, maxdown = 1, ip_addr = '', port = 8080):
   global maxdownloads

   maxdownloads = maxdown

   # We have to somehow push the filename of the file to serve to the
   # class handling the requests. This is an evil way to do this...

   FileServHTTPRequestHandler.filename = filename

   try:
      httpd = ForkingHTTPServer ((ip_addr, port), FileServHTTPRequestHandler)
   except socket.error:
      print >>sys.stderr, "cannot bind to IP address '%s' port %d" % (ip_addr, port)
      sys.exit (1)

   if not ip_addr:
      ip_addr = find_ip ()
   if ip_addr:
      if filename:
         location = "http://%s:%s/%s" % (ip_addr, httpd.server_port,
                                         urllib.quote (os.path.basename (filename)))
         if os.path.isdir (filename):
            if compressed == 'gz':
               location += ".tar.gz"
            elif compressed == 'bz2':
               location += ".tar.bz2"
            elif compressed == 'zip':
               location += ".zip"
            else:
               location += ".tar"
      else:
         location = "http://%s:%s/" % (ip_addr, httpd.server_port)

      print "Now serving on %s" % location

   while cpid != 0 and maxdownloads > 0:
      httpd.handle_request ()



def usage (defport, defmaxdown, errmsg = None):
   name = os.path.basename (sys.argv[0])
   print >>sys.stderr, """
    Usage: %s [-i <ip_addr>] [-p <port>] [-c <count>] <file>
           %s [-i <ip_addr>] [-p <port>] [-c <count>] [-z|-j|-Z|-u] <dir>
           %s [-i <ip_addr>] [-p <port>] [-c <count>] -s
           %s [-i <ip_addr>] [-p <port>] [-c <count>] -U

           %s <url>
   
    Serves a single file <count> times via http on port <port> on IP
    address <ip_addr>.
    When a directory is specified, an tar archive gets served. By default
    it is gzip compressed. You can specify -z for gzip compression, 
    -j for bzip2 compression, -Z for ZIP compression or -u for no compression.
    You can configure your default compression method in the configuration 
    file described below.

    When -s is specified instead of a filename, %s distributes itself.

    When -U is specified, woof provides an upload form, allowing file uploads.
   
    defaults: count = %d, port = %d

    If started with an url as an argument, woof acts as a client,
    downloading the file and saving it in the current directory.

    You can specify different defaults in two locations: /etc/woofrc
    and ~/.woofrc can be INI-style config files containing the default
    port and the default count. The file in the home directory takes
    precedence. The compression methods are "off", "gz", "bz2" or "zip".

    Sample file:

        [main]
        port = 8008
        count = 2
        ip = 127.0.0.1
        compressed = gz
   """ % (name, name, name, name, name, name, defmaxdown, defport)

   if errmsg:
      print >>sys.stderr, errmsg
      print >>sys.stderr
   sys.exit (1)



def woof_client (url):
   urlparts = urlparse.urlparse (url, "http")
   if urlparts[0] not in [ "http", "https" ] or urlparts[1] == '':
      return None

   fname = None

   f = urllib.urlopen (url)

   f_meta = f.info ()
   disp = f_meta.getheader ("Content-Disposition")

   if disp:
      disp = disp.split (";")

   if disp and disp[0].lower () == 'attachment':
      fname = [x[9:] for x in disp[1:] if x[:9].lower () == "filename="]
      if len (fname):
         fname = fname[0]
      else:
         fname = None

   if fname == None:
      url = f.geturl ()
      urlparts = urlparse.urlparse (url)
      fname = urlparts[2]

   if not fname:
      fname = "woof-out.bin"

   if fname:
      fname = urllib.unquote (fname)
      fname = os.path.basename (fname)

   readline.set_startup_hook (lambda: readline.insert_text (fname))
   fname = raw_input ("Enter target filename: ")
   readline.set_startup_hook (None)

   override = False

   destfile = None
   destfilename = os.path.join (".", fname)
   try:
      destfile = os.open (destfilename,
                          os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0644)
   except OSError, e:
      if e.errno == errno.EEXIST:
         override = raw_input ("File exists. Overwrite (y/n)? ")
         override = override.lower () in [ "y", "yes" ]
      else:
         raise

   if destfile == None:
      if override == True:
         destfile = os.open (destfilename, os.O_WRONLY | os.O_CREAT, 0644)
      else:
         for suffix in [".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9"]:
            destfilename = os.path.join (".", fname + suffix)
            try:
               destfile = os.open (destfilename,
                                   os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0644)
               break
            except OSError, e:
               if e.errno == errno.EEXIST:
                  continue
               raise

         if not destfile:
            destfile, destfilename = tempfile.mkstemp (prefix = fname + ".",
                                                    dir = ".")
         print "alternate filename is:", destfilename

   print "downloading file: %s -> %s" % (fname, destfilename)

   shutil.copyfileobj (f, os.fdopen (destfile, "w"))

   return 1;



def main ():
   global cpid, upload, compressed

   maxdown = 1
   port = 8080
   ip_addr = ''

   config = ConfigParser.ConfigParser ()
   config.read (['/etc/woofrc', os.path.expanduser ('~/.woofrc')])

   if config.has_option ('main', 'port'):
      port = config.getint ('main', 'port')

   if config.has_option ('main', 'count'):
      maxdown = config.getint ('main', 'count')

   if config.has_option ('main', 'ip'):
      ip_addr = config.get ('main', 'ip')

   if config.has_option ('main', 'compressed'):
      formats = { 'gz'    : 'gz',
                  'true'  : 'gz',
                  'bz'    : 'bz2',
                  'bz2'   : 'bz2',
                  'zip'   : 'zip',
                  'off'   : '',
                  'false' : '' }
      compressed = config.get ('main', 'compressed')
      compressed = formats.get (compressed, 'gz')

   defaultport = port
   defaultmaxdown = maxdown

   try:
      options, filenames = getopt.getopt (sys.argv[1:], "hUszjZui:c:p:")
   except getopt.GetoptError, desc:
      usage (defaultport, defaultmaxdown, desc)

   for option, val in options:
      if option == '-c':
         try:
            maxdown = int (val)
            if maxdown <= 0:
               raise ValueError
         except ValueError:
            usage (defaultport, defaultmaxdown, 
                   "invalid download count: %r. "
                   "Please specify an integer >= 0." % val)

      elif option == '-i':
         ip_addr = val

      elif option == '-p':
         try:
            port = int (val)
         except ValueError:
            usage (defaultport, defaultmaxdown,
                   "invalid port number: %r. Please specify an integer" % val)

      elif option == '-s':
         filenames.append (__file__)

      elif option == '-h':
         usage (defaultport, defaultmaxdown)

      elif option == '-U':
         upload = True

      elif option == '-z':
         compressed = 'gz'
      elif option == '-j':
         compressed = 'bz2'
      elif option == '-Z':
         compressed = 'zip'
      elif option == '-u':
         compressed = ''

      else:
         usage (defaultport, defaultmaxdown, "Unknown option: %r" % option)

   if upload:
      if len (filenames) > 0:
         usage (defaultport, defaultmaxdown,
                "Conflicting usage: simultaneous up- and download not supported.")
      filename = None

   else:
      if len (filenames) == 1:
         if woof_client (filenames[0]) != None:
            sys.exit (0)

         filename = os.path.abspath (filenames[0])
      else:
         usage (defaultport, defaultmaxdown,
                "Can only serve single files/directories.")

      if not os.path.exists (filename):
         usage (defaultport, defaultmaxdown,
                "%s: No such file or directory" % filenames[0])

      if not (os.path.isfile (filename) or os.path.isdir (filename)):
         usage (defaultport, defaultmaxdown,
                "%s: Neither file nor directory" % filenames[0])

   serve_files (filename, maxdown, ip_addr, port)

   # wait for child processes to terminate
   if cpid != 0:
      try:
         while 1:
            os.wait ()
      except OSError:
         pass



if __name__=='__main__':
   try:
      main ()
   except KeyboardInterrupt:
      print

