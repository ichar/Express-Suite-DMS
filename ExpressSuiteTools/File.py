"""
Implementation of the file attachments for the documents.

'FileAttachment' class -- file attachment implementation.
'addFile' function -- handles upload of a new file object and attaches it to the container.

$Id: File.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 21/01/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import re
from cStringIO import StringIO
from ntpath import basename as nt_basename, splitext as nt_splitext
from types import StringType, UnicodeType

import OFS.Image
from AccessControl import ClassSecurityInfo
from Acquisition import aq_base, aq_get, aq_inner, aq_parent
from Globals import DTMLFile
from OFS.Image import File
from ZPublisher.HTTPRequest import FileUpload

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.Expression import Expression
from Products.CMFCore.utils import getToolByName

import Config, Features
from ActionsTool import ActionInformation
from Exceptions import SimpleError
from Features import createFeature
from ImageAttachment import ImageAttachment
from SimpleObjects import ContentBase
from Utils import InitializeClass, extractBody, translit_string

SEACHABLE_TEXT_DISABLED = 1
manage_addAttachmentForm = DTMLFile( 'dtml/imageAdd', OFS.Image.__dict__, Kind='Attachment' )


def manage_addAttachment( self, id, file='', title='', filename=None, content_type='', REQUEST=None ):
    """
        Creates a new FileAttachment object and inserts it into the container.

        Arguments:

            'id' -- identifier string of the new object

            'file' -- optional FileUpload object or string;
                      if not given, the object is created with
                      empty contents

            'title' -- optional title of the object;
                       empty by default

            'filename' -- optional name of the file to be stored
                          in the respective object property;
                          if not given, the method tries to obtain
                          it from the FileUpload object or uses 'id'
                          value as a last resort

            'content_type' -- optional MIME type of the file contents

            'REQUEST' -- optional Zope request object

        Result:

            Redirect to the main management screen of the container
            if REQUEST is specified.
    """
    # XXX make this work
    #if not isinstance( self, SimpleAppItem ):
    #    raise TypeError, 'This object cannot contain attachments.'

    id = str(id)
    title = str(title)
    content_type = str(content_type)

    # first, create the file without data:
    self._setObject( id, FileAttachment( id, title, '', content_type ) )
    ob = self._getOb( id )

    if not filename:
        filename = isinstance( file, FileUpload ) and file.filename or id
    ob._setPropValue( 'filename', nt_basename( filename ) )

    # Now we "upload" the data.  By doing this in two steps, we
    # can use a database trick to make the upload more efficient.
    if file:
        ob.manage_upload( file )

    # force given content type
    if content_type:
        ob._setPropValue( 'content_type', content_type )

    ob.reindexObject()

    if REQUEST is not None:
        REQUEST.RESPONSE.redirect( self.absolute_url() + '/manage_main' )


_text_types = []
              #Converter.TextConverter.content_types + \
              #Converter.MSWordConverter.content_types + \
              #Converter.HTMLConverter.content_types  + \
              #Converter.RTFConverter.content_types + \
              #Converter.MSExcelConverter.content_types + \
              #Converter.MSPowerPointConverter.content_types
              #Converter.PDFConverter.content_types


class FileAttachment( ContentBase, File ):
    """
        File attachment class.

        Implementation of the file object attached to the main document
        or other container.  File attachment has its own UID and has
        a searchable record in the portal catalog.

        This object support upload and download operations and can be used
        as an external source of the main document text.
    """
    _class_version = 1.0

    meta_type = 'File Attachment'
    portal_type = 'File Attachment'

    security = ClassSecurityInfo()

    __implements__ = createFeature('isFileAttachment'), \
                     Features.isAttachment, \
                     ContentBase.__implements__, \
                     File.__implements__

    _actions = ContentBase._actions + ( \
            ActionInformation(
                id='external_edit',
                title='External edit',
                icon='/misc_/ExternalEditor/edit_icon',
                action=Expression( 'string: ${object_url}/externalEdit' ),
                permissions=( CMFCorePermissions.ModifyPortalContent, ),
                condition=Expression("python: not request.get('HTTPS')"),
                category='object',
                visible=1,
            ),
        )

    _properties = ContentBase._properties + \
                  File._properties[1:] + \
                  (
                      {'id':'filename', 'type':'string'},
                  )

    # default attribute values
    filename = None
    _extension = ''

    # access rights of the owner are determined by the parent document
    _owner_role = None

    # overriden by PortalContent in ContentBase
    __len__ = File.__len__

    # for use by the external editor
    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'PUT' )
    PUT = File.PUT

    def __init__( self, id, title, file, content_type='' ):
        """
            Creates a new FileAttachment instance.

            Arguments:

                'id' -- identifier string of the object

                'file' -- either FileUpload object or string data
                          for the file contents

                'title' -- title of the object

                'content_type' -- optional MIME type of the file

        """
        ContentBase.__init__( self, id )

        #full name we get here is already recoded
        self._extension = nt_splitext( id )
        while self._extension and self._extension[0]=='.':
            self._extension = self._extension[1:]

        File.__init__( self, id, title, file, content_type )

    def _initstate( self, mode ):
        # initialize attributes
        if not ContentBase._initstate( self, mode ): return 0
        # versions < 1.2 used __name__ for id
        if not self.id: self.id = self.__name__
        return 1

    def __nonzero__( self ):
        # used to override __len__
        return 1

    def _setId( self, id ):
        # we need this because File is Item_w__name__
        ContentBase._setId( self, id )
        File._setId( self, id )

    def getBase( self ):
        return aq_parent(aq_inner(self))

    def view( self, REQUEST=None ):
        """
            Implements the default view of the file contents.

            Arguments:

                'REQUEST' -- optional Zope request object

            Result:

                See 'index_html' method description.
        """
        REQUEST = REQUEST or self.REQUEST
        return self.index_html( REQUEST, REQUEST.RESPONSE )

    def index_html( self, REQUEST, RESPONSE ):
        """
            Returns the contents of the file.

            Sets 'Content-Type' header in the response to the object's
            content type.  Sets value of the 'Content-Disposition' header
            to either 'inline' or 'attachment' accordingly to the file type,
            and a 'filename' parameter to the real name of the file.

            Arguments:

                'REQUEST' -- Zope request object

                'RESPONSE' -- Zope response object

            Result:

                String containing the file data.
        """
        ctype = self.getContentType()
        ctype = ctype and ctype.split('/')[0]
        fname = self.getProperty('filename') or self.getId()

        RESPONSE.setHeader( 'Content-Disposition', '%s; filename="%s"; size="%d"' % \
                ( ctype == 'text' and 'inline' or 'attachment', fname, self.getSize() ) )

        return File.index_html( self, REQUEST, RESPONSE )

    security.declareProtected( CMFCorePermissions.View, 'RawBody' )
    def RawBody( self ):
        """
            Returns raw file data.

            Result:

                String (potentially big).
        """
        return str( self )

    security.declareProtected( CMFCorePermissions.View, 'CookedBody' )
    def CookedBody( self, format='text' ):
        """
            Extracts text from the file contents and returns it in the requested format.

            Arguments:

                'format' -- optional output format specifier, 'html' and 'text'
                            (used by default) are supported

            Result:

                String respesenting the file text.
        """
        if not self.isTextual():
            return ''
        text = str(self) #Converter.convert( str(self), self.getContentType(), format=format, context=self )
        if format == 'html':
            # we show document in frame thus we need text inside BODY tag
            text = extractBody( text )
        return text

    security.declareProtected( CMFCorePermissions.View, 'isTextual' )
    def isTextual( self ):
        """
            Checks whether the file contents can be represented as text.

            For example, '*.doc', '*.rtf', '*,html', '*.txt' are considered
            textual.  Depends on the installed document converters.

            Result:

                Boolean value, true if the file is textual.
        """
        return self.getContentType() in _text_types

    def update_data( self, data, content_type=None, size=None ):
        # private method for changing file contents;
        # notifies container document that is should update its text
        # in case this file is used as the text source.
        File.update_data( self, data, content_type, size )
        parent = self.parent()
        if parent is not None and parent.implements('isCompositeDocument'):
            parent._notifyAttachChanged( self.getId() )

    def Extension( self ):
        """ 
            Returns extention of object
        """
        id = self.getId()
        try: extension = nt_splitext( id )[1][1:]
        except: extension = getattr( self, '_extension', None )
        return extension

    def SearchableText( self ):
        """ 
            Returns indexable text for the fulltext search
        """
        id = self.getId()
        if SEACHABLE_TEXT_DISABLED:
            text = '%s %s %s' % ( self.Title(), id, self.Extension() )
        else:
            #try:
            #    text = '%s %s' % ( id, self.CookedBody( format='text' ) )
            #except Converter.ConverterError:
            #    text = id
            pass
        if hasattr(self, 'getBase'):
            base = self.getBase()
            text = '%s %s %s %s' % ( base.Title(), base.Description(), \
                hasattr(base, 'registry_numbers') and base.registry_numbers() or '', \
                text )
        return text

    def getIcon( self, ex_icon = '' ):
        """
            Returns the file type sensitive icon.

            Arguments:

                'ex_icon' -- String. Uses when _extension is exist.

            Result:

                String.
        """
        if self._extension != '':
            self._extension = ex_icon

        if self._extension.lower() in [ 'gif', 'jpg' ]:
            icon = Config.Icon2FileMap.get(self._extension.lower())
        else:
            icon = 'file.gif'

        return icon

InitializeClass( FileAttachment )


def addFile( self, id=None, file=None, title=None, REQUEST=None, unresticted=None, **kw ):
    """
        Handles upload of a new file object and attaches it to the container.

        Arguments:

            'id' -- optional identifier string of the new object;
                    if not given, generated from either 'title'
                    or filename of the FileUpload, or by random
                    if neither is suitable

            'file' -- FileUpload object or string data for the
                      attachment contents

            'title' -- optional title of the object;
                       is set to filename by default

            'REQUEST' -- optional Zope request object

        Result:

            Identifier string of the new attachment object.
    """
    if file is None:
        return None

    self.failIfLocked()

    idx = nidx = 0
    filename = isinstance( file, FileUpload ) and nt_basename( file.filename ) or None
    old_suffix = None

    if not id:
        lang = getToolByName( self, 'portal_membership' ).getLanguage( REQUEST=REQUEST )
        id = translit_string( filename or title, lang )
        basename = suffix = ''

        if id:
            # replace illegal characters
            id = re.sub( r'^[^a-zA-Z0-9\.]+|[^a-zA-Z0-9-_~\,\.]+', '', id )
            if filename:
                basename, suffix = nt_splitext( id )
                if not basename:
                    id = None
            elif id:
                basename = id
        if not basename:
            nidx = 1
            basename = 'file'

        # place an original filename to the object's id
        # and change it to the sequental number
        while not ( id and self._getOb( id, None ) is None ):
            idx += 1
            id = '%s_%03d%s' % ( basename, idx, suffix )

    basename, suffix = nt_splitext( filename or id )
    suffix = old_suffix or suffix.lower()

    if title is None:
        title = re.sub( r'[\s_]+', ' ', basename.strip() )
        if title and idx > nidx:
            title += ' [%d]' % (idx - nidx)
    if not title:
        title = id

    # Choose the way to add the file and attach it to the document
    if not unresticted and suffix in Config.NoEmailedExtensions:
        raise SimpleError, 'This object cannot be mailed later. Please pack it before.'
    elif suffix in Config.ImageExtensions:
        if Config.UsePILImage:
            if type(file) in ( StringType, UnicodeType ):
                file = StringIO( file )

            img = ImageAttachment(id, title=title, file=file, engine='PIL', quality=95, timeout=0)
            self._setObject(id, img)

            if suffix in ['.tif', '.tiff']:
                tiff_img = self._getOb(id)
                tiff_img._original.content_type = 'image/tiff'
                tiff_img._is_TIFF = 1
                tiff_img._p_changed = 1

        else:
            self.manage_addImage( id, file=file, title=title )
    else:
        # XXX
        self.manage_addProduct['ExpressSuiteTools'].manage_addAttachment( id, file=file, title=title, \
                REQUEST=REQUEST, **kw )

    return id

def initialize( context ):
    # register FileAttachment constructor as a Zope factory
    context.registerClass(
        FileAttachment,
        permission = CMFCorePermissions.ModifyPortalContent,
        constructors = ( manage_addAttachmentForm, manage_addAttachment ),
        icon = 'icons/file_icon.gif',
    )
