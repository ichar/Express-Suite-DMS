"""
HTMLDocument class
$Id: HTMLDocument.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 18/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from sys import version_info
if version_info[:2] < (2, 3):
    import pre as re
else:
    import re

import threading
from cgi import escape
from ntpath import basename as nt_basename, splitext as nt_splitext
from types import ListType, StringType, TupleType
from random import random
from urlparse import urlparse

from AccessControl import ClassSecurityInfo, Permissions as ZopePermissions
from Acquisition import aq_base, aq_parent, aq_get, Implicit
from DateTime import DateTime
from OFS.ObjectManager import ObjectManager
from Globals import DTMLFile
from webdav.LockItem import LockItem
from ZODB.POSException import ConflictError

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.CMFCatalogAware import CMFCatalogAware
from Products.CMFCore.PortalFolder import PortalFolder
from Products.CMFCore.utils import getToolByName, _getViewFor, _getAuthenticatedUser, _checkPermission
from Products.CMFDefault.Document import Document
from Products.CMFDefault.utils import html_headcheck, formatRFC822Headers

import Config, Features, Exceptions
from Config import Roles, Months, Permissions, TaskResultCodes, TaskCommits, DemandRevisionCodes
from ConflictResolution import ResolveConflict
from ContentVersions import VersionableContent, InitializeVersionableClass
from DiscussionItem import DiscussionItemContainer
from Features import createFeature
from File import FileAttachment, addFile as _addFile
from HTMLCleanup import HTMLCleaner
from HTMLDiff import HTMLDiff
from ImageAttachment import ImageAttachment
from Mail import MailMessage, getContentId
from SimpleAppItem import SimpleAppItem
from PortalLogger import portal_log, portal_info, portal_debug, portal_error
from TaskItem import TaskItemContainer
from WorkflowTool import WorkflowMethod

from Utils import InitializeClass, getLanguageInfo, joinpath, isBroken, getClientStorageType, getPlainText, \
     getObjectByUid, formatComments, parseTitle, parseDate, parseMemberIDList, uniqueValues

from CustomDefinitions import PortalInstance, CustomDocumentTagNames, CustomFacsimileTagNames, \
     CustomAttachmentTagNames, CustomDefaultLogo, CustomFaxEmail
from CustomObjects import ObjectHasCustomCategory, CustomCategoryPostfix, ResolutionBackgroundColor, \
     TranslateCustomBody, CustomCookedTable, CustomCookedTableNotifyOnChange, IsPrivateObject, \
     CookedBodyTag

SYSTEM_FIELDS = ( \
                    'sysRegNo', 'sysRegDate', 'sysDescr', 'sysDescription', 'sysCreator', 'sysReplyTo', 'sysPrivate',
                    'sysContent', 'sysContentDirective', 'sysContentInformation', 'sysContentRequest', 'sysContentSignature_Request',
                    'sysFollowup', 'sysFollowupSignature_Request', 'sysFollowupInformation', 'sysFollowupRequest', 
                    'sysFollowupRequestWithNotifications', 
                )

timeout = 3.0
default_content_type = 'text/html'

factory_type_information = ( 
                            { 'id'              : 'HTMLDocument'
                            , 'meta_type'       : 'HTMLDocument'
                            , 'title'           : 'Document'
                            , 'description'     : """HTML-document with WYSIWYG editor"""
                            , 'icon'            : 'doc_icon.gif'
                            , 'sort_order'      : 0.4
                            , 'product'         : 'ExpressSuiteTools'
                            , 'factory'         : 'addHTMLDocument'
                            , 'immediate_view'  : 'document_edit_form'
                            , 'allow_discussion': 1
                            , 'actions'         :
                                ( { 'id'            : 'view'
                                  , 'name'          : 'View'
                                  , 'action'        : 'document_view'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'followup'
                                  , 'name'          : 'Follow-up tasks'
                                  , 'action'        : 'document_follow_up_form'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'register'
                                  , 'name'          : 'Register'
                                  , 'action'        : 'document_registration_form'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'edit'
                                  , 'name'          : 'Edit'
                                  , 'action'        : 'document_edit_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  , 'condition'     : 'python: object.checkVersionModifyPerm()'
                                  }
                                , { 'id'            : 'request_confirmation'
                                  , 'name'          : 'Request confirmation'
                                  , 'action'        : 'document_confirmation_form'
                                  , 'permissions'   : ( CMFCorePermissions.RequestReview, )
                                  }
                                , { 'id'            : 'metadata'
                                  , 'name'          : 'Metadata'
                                  , 'action'        : 'metadata_edit_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  }
                                , { 'id'            : 'attachments'
                                  , 'name'          : 'Attachments'
                                  , 'action'        : 'document_attaches'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'link'
                                  , 'name'          : 'Links'
                                  , 'action'        : 'document_link_form'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'ownership'
                                  , 'name'          : 'Change ownership'
                                  , 'action'        : 'change_ownership_form'
                                  , 'permissions'   : ( ZopePermissions.take_ownership, )
                                  }
                                , { 'id'            : 'distribute_document'
                                  , 'name'          : 'Distribute document'
                                  , 'action'        : 'distribute_document_form'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'distribution_log'
                                  , 'name'          : 'Distribution log'
                                  , 'action'        : 'distribution_log_form'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                , { 'id'            : 'export_document'
                                  , 'name'          : 'Export document'
                                  , 'action'        : 'export_import_form'
                                  , 'permissions'   : ( CMFCorePermissions.ModifyPortalContent, )
                                  }
                                , { 'id'            : 'reply_to_document'
                                  , 'name'          : 'Reply to document'
                                  , 'action'        : 'reply_to_document'
                                  , 'permissions'   : ( CMFCorePermissions.View, )
                                  }
                                )
                            }
                           ,
                           )

_formattedBodyTemplate = """
<html>
<head>
%(head)s
<title>%(title)s</title>
<style type="text/css">
body {
    font-family: %(font)s;
    color: black;
}
body, table {
    font-size: 10px;
}
</style>
%(style)s
</head>
<body lang="%(language)s" bgcolor="#ffffff">
%(resolution)s
%(body)s
</body>
</html>
"""

_formattedResolutionStyle = """
<style type="text/css">
div.resolution_container {
    font-family: Times New Roman;
    position: absolute;
    right: 20px;
    top: 40px;
    width: 60%;
}
</style>
"""

_formattedResolutionStyle_no_absolute = """
<style type="text/css">
div.resolution_container {
    font-family: Times New Roman;
    width: 100%;
}
</style>
"""

_formattedResolutionTemplate = """
<style type="text/css">
div.resolution_container table {
    border-top: 1pt solid #a0a0a0;
    border-left: 1pt solid #a0a0a0;
    border-bottom: 2pt solid #a0a0a0;
    border-right: 2pt solid #a0a0a0;
    width: 100%;
}
div.resolution_container em {
    font-family: Times New Roman;
    font-size: 14px;
    color: purple;
    line-height: 100%; 
    text-align: left;
    font-style: italic;
}
div.resolution_container p {
    font-family: Times New Roman;
    font-size: 12px;
    TEXT-INDENT: 0px;
    text-align: left;
}
</style>

<script type="text/javascript">
<!--
function show_resolution(id) {
  if(typeof(document.all[id]) != 'object') return;
  var obj = document.all[id];
  obj.style.display = (obj.style.display == 'block' ? 'none' : 'block');
}
//-->
</script>
"""

_formattedResolutionContainer = """
<DIV class=resolution_container id=resolution_body style="DISPLAY:%(display)s;">
%(text)s
</DIV>
"""

_formattedResolutionText = """
<TABLE cellSpacing=10 cellPadding=0 bgcolor=%(color)s border=0>
<TBODY>
<TR><TD><P><STRONG>Резолюция по документу:%(title)s</STRONG><BR>К исполнению:&nbsp;<STRONG>%(involved)s</STRONG>, срок&nbsp;%(expires)s</P></TD></TR>
<TR><TD><EM>%(text)s</EM></TD></TR>
<TR><TD><P>Автор резолюции:<BR><STRONG>%(author)s</STRONG></P></TD></TR>
<TR><TD><P>%(date)s</P></TD></TR></TBODY></TABLE>
"""

_embedded_view_scripts = """"""
_embedded_edit_scripts = """"""

MagicSaveTransition = '__save__'


def addHTMLDocument( self, id, title='', description='', text_format='html', text='', attachments=() ):
    """ 
        Add an HTML document (invoke factory constructor).

        Arguments:

            'attachments' -- list of file objects to attach to the document
    """
    o = HTMLDocument( id, title, description, text_format, text )

    IsError = 0
    repeat_action = 0
    ob = None
    msg = ''
    n = 0

    while n < 3:
        n += 1
        try:
            self._setObject( id, o )
            ob = self._getOb( id )
            IsError = 0
            break

        except Exception, message:
            IsError = 1
            msg = str(message)
            if not repeat_action:
                break
            portal_error( 'HTMLDocument.addHTMLDocument', '%s, id: %s' % ( msg, id ), exc_info=True )
            threading.Event().wait( timeout*n )
            continue

    try: path = ob is not None and ob.physical_path() or ''
    except: path = ''

    if not IsError:
        for idx in range( len(attachments) ):
            file = attachments[ idx ]
            params = {}
            if isinstance( file, TupleType ):
                file, params = file

            new_id = ob.addFile( file=file, **params )

        portal_info( 'HTMLDocument.addHTMLDocument', 'successfully created new document, path: %s' % path )
    else:
        portal_error( 'HTMLDocument.addHTMLDocument', '%s, id: %s, path: %s' % ( msg or 'exception', id, path ) )

    del o, ob


class HTMLDocument( VersionableContent, SimpleAppItem, ObjectManager, Document ):
    """
        Subclassed Document type
    """
    _class_version = 1.0

    meta_type = 'HTMLDocument'
    portal_type = 'HTMLDocument'

    __implements__ = ( createFeature('isHTMLDocument'),
                       Features.isDocument,
                       Features.isCompositeDocument,
                       Features.isPublishable,
                       Features.isLockable,
                       Features.hasLanguage,
                       Features.isPrintable,
                       SimpleAppItem.__implements__,
                       Document.__implements__,
                       ObjectManager.__implements__,
                       VersionableContent.__implements__,
                     )

    security = ClassSecurityInfo()

    # override access settings
    security.declareProtected( CMFCorePermissions.View, 'Format' )

    manage_options = SimpleAppItem.manage_options + \
                     Document.manage_options + \
                     ObjectManager.manage_options

    # A list of supported MIME types for the document content, in order of preference
    allowed_content_types = ( 'text/html', 'text/plain', )

    # default attribute values
    #document_subscription_announce = DTMLFile( 'skins/mail_templates/document_subscription_announce', globals() )

    _versionable_methods = (
            'getChangesFrom', 'addFile', 'pasteFile', 'removeFile', 'listAttachments', 'associateWithAttach', '_replaceLinks'
        )

    _versionable_methods_common = (
            'absolute_url', 'relative_url', 'redirect',
        )

    _versionable_attrs = (
            'text', 'cooked_text', 'title', 'description',
            'modification_date', 'effective_date', 'creation_date',
            'associated_with_attach', 'attachments',
            'workflow_history', '__propsets__',
        )

    _versionable_perms = (
            CMFCorePermissions.View,
            CMFCorePermissions.ModifyPortalContent,
            Permissions.MakeVersionPrincipal,
        )

    edit = WorkflowMethod( Document.edit, 'modify', \
                           security=security, \
                           method_permission=CMFCorePermissions.ModifyPortalContent, \
                           invoke_after=1 )

    # restore ObjectManager methods overridden by PortalContent
    objectItems = ObjectManager.objectItems
    objectValues = ObjectManager.objectValues
    tpValues = ObjectManager.tpValues

    # restore Document methods overridden by DublinCore
    Format = Document.Format
    #setFormat = Document.setFormat
    getMetadataHeaders = Document.getMetadataHeaders

    def reindex( self ):
        """
            Apply extra (recursive) reindex for this object
        """
        ob = self.getVersionable()
        if ob is None:
            return 'Object is None!'
        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is not None:
            catalog.reindexObject(ob, recursive=1)
        followup = getToolByName( self, 'portal_followup', None )
        if followup is not None:
            followup.reindexObject(ob, recursive=1)
        return 'OK.'

    def __init__( self, id, title='', description='', text_format='html', text='' ):
        """
            Initialize class instance
        """
        VersionableContent.__init__( self ) # must be first
        SimpleAppItem.__init__( self )
        Document.__init__( self, id, parseTitle(title), description, text_format, text )

    # CHECK THE OBJECT STATES AND ADVISABLE IGNORE CONFLICT !!!
    # =========================================================
    def _p_resolveConflict( self, o, s, n ):
        return ResolveConflict('HTMLDocument', o, s, n, 'modification_date', mode=-1, trace=0, default=1)

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not SimpleAppItem._initstate( self, mode ):
            return 0

        if getattr( self, 'changes_log', None ) is None:
            self.changes_log = []

        if hasattr( self, '_directive' ):
            delattr( self, '_directive' )

        followup = getattr( self, 'followup', None )
        if followup is None or not isinstance( followup, TaskItemContainer ):
            self.followup = TaskItemContainer()

        talkback = getattr(self, 'talkback', None)
        if talkback is None or not isinstance(talkback, DiscussionItemContainer):
            self.talkback = DiscussionItemContainer()

        for id, item in self.objectItems():
            if isinstance( item, PortalFolder ):
                self._delObject( id )
            if isBroken( item, 'SearchableAttach' ):
                self._upgrade( id, FileAttachment )

        if hasattr( self, 'registry_id' ):
            self.registry_data = {}
            self.registry_data[ self.registry_id ] = ['Not specified']
            delattr( self, 'registry_id' )
        elif hasattr( self, 'registry_data' ):
            for key in self.registry_data.keys():
                if type(self.registry_data[ key ]) is not ListType:
                    self.registry_data[ key ] = [ self.registry_data[ key ] ]
        else:
            self.registry_data = {}

        if not hasattr( self, 'subscribed_users'):
            self.subscribed_users = {}

        if not hasattr( self, 'selected_template'):
            self.selected_template = None

        if type(self.subscribed_users) is ListType:
            new_su = {}
            for user in self.subscribed_users:
                new_su[ user ] = [ MagicSaveTransition ]

            self.subscribed_users = new_su

        if not hasattr( self, 'distribution_log' ):
            self.distribution_log = []

        base = aq_base( self )
        if hasattr( base, 'workflow_history' ):
            # copying workflow_history from document to principal version
            self.getVersion( self.getPrincipalVersionId() ).workflow_history = getattr( base, 'workflow_history' )
            # deleting workflow_history from document
            try:
                del self.workflow_history
                self._p_changed = 1
            except:
                pass

            # initializing followup tasks
            version_id_to_initialize = self.getPrincipalVersionId()
            for task in self.followup.objectValues():
                if not hasattr( task, 'version_id' ):
                    task.version_id = version_id_to_initialize
                elif task.version_id is None:
                    task.version_id = version_id_to_initialize

        return 1

    def __before_publishing_traverse__( self, object, REQUEST ):
        """
            Allow subobjects to be called
        """
        path = REQUEST['TraversalRequestNameStack']

        if len(path) > 1 and path[-1] == self.getId():
            del path[-1]

    def Language( self ):
        """
            Returns document language code
        """
        return Document.Language( self ) or getToolByName( self, 'msg' ).get_default_language()

    security.declarePublic( 'getFontFamily' )
    def getFontFamily( self ):
        """
            Returns font family names for the document text
        """
        return getLanguageInfo( self.Language() )['document_font']

    security.declareProtected( CMFCorePermissions.View, 'SearchableText' )
    def SearchableText( self ):
        """
            Used by the catalog for basic full text indexing.
            We should check type of object: document or attachment. Indexing may be applied for every type.
            We exclude seachable text for files and images.
        """
        if self.implements('isHTMLDocument'):
            body = getPlainText( self.CookedBody( view=1, no_update=1 ) ) #EditableBody()
            body = re.sub(r'\[(.*?)\]', '', body)
            body = re.sub(r'[\f\r\t\v\n ]+', ' ', body)
            if ObjectHasCustomCategory( self ) and not self.IsSystemObject( no_authenticate=1 ):
                return '%s %s %s %s' % ( self.registry_numbers(original=0), self.Title(), body, self.getAttachmentsInfo() )
            return '%s %s %s' % ( self.Title(), self.Description(), body )
        return '%s %s' % ( self.Title(), self.Description() )

    security.declareProtected( CMFCorePermissions.View, 'FormattedBody' )
    def FormattedBody( self, html=1, width=None, canonical=None, REQUEST=None ):
        """
            Returns formatted document body.

            Arguments:

                'html'      -- Boolean. Indicates whether the document text should be
                               formatted according to the HTML rules.

                'width'     -- Not implemented. Specifies the maximum string width.

                'canonical' -- Boolean. Forces external links to be rendered in a
                               canonical way. See ItemBase.absolute_url for details.

            Result:

                String.

        """
        lang = self.Language()
        charset = getLanguageInfo( lang )['http_charset']

        if REQUEST is not None:
            REQUEST.RESPONSE.setHeader( 'content-type', 'text/html; charset=%s' % charset )

        if html or self.text_format == 'html':
            site_style = '<link rel=\"stylesheet\" type=\"text/css\" href=\"' + self.portal_url() + '/dynamic_stylesheet\" />\n'

            if canonical:
                meta = '<meta http-equiv="Content-Type" content="text/html; charset=%s" />\n' % charset
            else:
                meta = ''

            bodytext = _formattedBodyTemplate % {
                        'title'     : escape( self.Title() ),
                        'head'      : meta,
                        'style'     : site_style,
                        'language'  : lang,
                        'font'      : self.getFontFamily(),
                        'resolution': '',
                        'body'      : self.CookedBody( canonical=canonical, view=1 ),
                    }
        else:
            bodytext = self.EditableBody( view=1 )

        if width is not None:
            # TODO: reformat width
            pass

        print_only = REQUEST is not None and REQUEST.get('print_only', None) and 1 or 0

        if print_only:
            r_hint = re.compile( r'(FOLLOWUP[^>]*DISPLAY\s*:\s*)block([^>]*>)', re.I+re.DOTALL )
            bodytext = self.RunRESub( bodytext, rfrom=r_hint, rto=r'\1none\2', mode=2 )

        return bodytext

    def listCategoryMetadata( self ):
        postfix = CustomCategoryPostfix(self)
        return postfix and [ ('postfix', postfix) ] or None

    def getDocumentResolution( self, display=None, no_absolute=None, tasks=None ):
        """
            Returns the document resolution text
        """
        if not ObjectHasCustomCategory( self ):
            return ''

        if tasks is None and getattr(self, 'followup', None) is not None:
            tasks = self.followup.getBoundTasks( recursive=1, sort=1 )
        if not tasks:
            return ''

        IsResolution = 0
        document_resolution = {}
        membership = getToolByName( self, 'portal_membership', None )

        resolution = ''
        color = ResolutionBackgroundColor()
        style = no_absolute and _formattedResolutionStyle_no_absolute or _formattedResolutionStyle
        title = '' #'<BR>%s' % self.Title()

        for task in tasks:
            task_resolution = task.getTaskResolution()
            if not task_resolution:
                continue
            text = re.sub( r'\n', r'<BR>', task.Description( view=1 ) or task.Title() )
            document_resolution['text'] = formatComments(text)
            try:
                involved = task.InvolvedUsers( no_recursive=1 ) or task.getTaskResolutionInvolvedUsers( with_groups=1 )
                document_resolution['involved'] = ', '.join( [ x['user_name'] for x in membership.listSortedUserNames( involved, mode='LFM' ) ] )
            except:
                document_resolution['involved'] = ''
            author = task_resolution['author']
            document_resolution['author'] = membership.getGroupOrMemberName( id=author )
            document_resolution['date'] = task_resolution['date']
            document_resolution['expires'] = task.expires()
            IsFinalized = task.isFinalizedSuccessfully()
            IsExpired = task.isExpired()
            IsResolution += 1

            if resolution:
                resolution += '<div><img src="spacer.gif" height="3"></div>'

            resolution += _formattedResolutionText % { \
                        'color'    : IsFinalized and color['finalized'] or IsExpired and color['expired'] or color['default'], \
                        'title'    : title, \
                        'involved' : document_resolution['involved'], \
                        'expires'  : document_resolution['expires'].strftime('%d.%m.%Y'), \
                        'text'     : document_resolution['text'], \
                        'author'   : document_resolution['author'], \
                        'date'     : document_resolution['date'], \
                    }

        if resolution:
            resolution = style + _formattedResolutionTemplate + _formattedResolutionContainer % { \
                        'display'  : display is None and 'block' or display, \
                        'text'     : resolution, \
                    }

        return resolution

    def body_view( self ):
        """
            It's used for simple document viewing
        """
        text = self.FormattedBody( canonical=1 )
        # Remove break in header part of template
        r_hint = re.compile( r'(<body[^>]*>\s+)(<BR>)(\s+<STYLE[^>]*>)', re.I+re.DOTALL )
        text = self.RunRESub( text, rfrom=r_hint, rto=r'\1\3', mode=2 )
        return text

    def CookedBody( self, stx_level=None, setlevel=0, resolution='block', canonical=None, view=None, \
                    no_update=None ):
        """
            Returns the prepared basic rendering of an object.

            For Documents, basic rendering means pre-rendered structured text, or
            what was between the <BODY> tags of HTML.

            Arguments:

                'stx_level'  -- Integer value for the stx text level.

                'setlevel'   -- Boolean. Indicates whether the document needs to
                                be recooked with new stx_level. See Document.CookedBody for
                                further explanations.

                'resolution' -- display status for the document resolution:
                                None - don't include in the text,
                                values - ['block', 'none'].

                'canonical'  -- Boolean. Forces external links to be rendered in a
                                canonical way. See ItemBase.absolute_url for details.

                'view' -- Boolean. This argument is passed to the _replaceLinks method.

            Result:

                String.
        """
        category = None

        try:
            selected_template = self.selected_template
        except:
            selected_template = None

        text = Document.CookedBody( self, stx_level, setlevel )
        text = self._replaceLinks( text, canonical=canonical, view=view )

        membership = getToolByName( self, 'portal_membership', None )
        metadata = getToolByName( self, 'portal_metadata', None )

        try:
            category = metadata.getCategoryById( self.Category() )
        except:
            pass

        archive = getClientStorageType( self )

        if category is not None:
            if selected_template is not None: # and not archive
                template_edit_fields_only = category.getEditMode( selected_template )
                template_use_translate = category.getTranslateMode( selected_template )
                template_use_facsimile = category.getFacsimileMode( selected_template )
            else:
                template_edit_fields_only = 0
                template_use_translate = 0
                template_use_facsimile = 0

            category_id = self.Category()
            IsCustomDocument = ObjectHasCustomCategory( self )
        else:
            return text
        #
        # Make macro-text processing for custom categories
        # Change border=1 to border=0 in TABLE tags having "border-collapse: collapse"
        #
        if IsCustomDocument and template_use_translate:
            r_table = re.compile( r'<TABLE[^>]*border-collapse\:\s+collapse;?[^>]*>', re.I )
            r_border = re.compile( r'border=\s*1', re.I)
            text = self.RunRESub( text, rfrom=r_table, rto=r_border, change_to='border=0' )

            r_hint = re.compile( r'(<TD[^>]*)height\:\s*\d*px([^>]*>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_hint, rto=r'\1\2', mode=2 )

            r_hint = re.compile( r'(<SPAN [^>]*display:\s*)block([^>]*>\[.*?\]</SPAN>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_hint, rto=r'\1none\2', mode=2 )

            r_hint = re.compile( r'(<SPAN id=com>\[.*?\]</SPAN>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_hint, rto=r'', mode=2 )

            r_hint = re.compile( r'(<SPAN>)\s*(&nbsp;)\s*(</SPAN>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_hint, rto=r'\1\2\3', mode=2 )
        #
        # Apply template transtating for CUSTOM_DOCUMENT_TITLE and CUSTOM_DOCUMENT_BODY html tags
        #
        if template_use_translate:
            matched = None
            document_tag_names = CustomDocumentTagNames()
            if not matched:
                rexp = r'<INPUT\s+.*?value="(.*?)"\s+.*name=%s[^>]*>' % document_tag_names[ 'title' ]
                r_title = re.compile( rexp, re.I+re.DOTALL )
                matched = r_title.search( text )
            if not matched:
                rexp = r'<INPUT\s+.*?name=%s[^>]*value="(.*?)">' % document_tag_names[ 'title' ]
                r_title = re.compile( rexp, re.I+re.DOTALL )
                matched = r_title.search( text )
            if matched:
                x = text[ matched.start(1) : matched.end(1) ]
                rexp = r'<SPAN name=%s>\1</SPAN><BR>' % document_tag_names[ 'title' ]
                text = r_title.sub( rexp, text )
            else:
                rexp = r'<INPUT\s+name=%s[^>]*>' % document_tag_names[ 'title' ]
                r_title = re.compile( rexp, re.I+re.DOTALL )
                matched = r_title.search( text )
                if not matched:
                    rexp = r'<INPUT\s+.*?name=%s>' % document_tag_names[ 'title' ]
                    r_title = re.compile( rexp, re.I+re.DOTALL )
                    matched = r_title.search( text )
                if matched:
                    rexp = r'<SPAN name=%s></SPAN><BR>' % document_tag_names[ 'title' ]
                    text = r_title.sub( rexp, text )

            PSTYLE = r''
            BRSTYLE = '\n</P><P' + PSTYLE + '>\n'

            rexp = r'(<)TEXTAREA\s+(.*name=%s[^>]*)(>)(.*?)(</)TEXTAREA(>)' % document_tag_names[ 'body' ]
            r_body = re.compile( rexp, re.I+re.DOTALL )
            matched = r_body.search( text )

            if matched:
                s = text[ matched.start(4) : matched.end(4) ]
                s = re.sub( r'<^>*>(?i)', '', s )
                s = re.sub( r'<^/>*/>(?i)', '', s )
                s = re.sub( r'\n', BRSTYLE, s )
                text = text[ :matched.start(4) ] + s + text[ matched.end(4): ]
                text = r_body.sub( r'\1P'+PSTYLE+r'\3\4\5P\6', text )

            r_hint = re.compile( r'(<P[^>]*>)\s*([A-Za-z0-9\-\0\.\)]+)\s*(.*?</P>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_hint, rto=r'\1<SPAN>\2</SPAN>&nbsp;\3', mode=2 )

            r_body = re.compile( r'(<P\s+class=no_br[^>]*>)(.*?)(</P>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_body, rto=r'', mode=5 )

            if self.creation_date < DateTime(2005, 11, 11):
                text = self.extra_cleaner( text )
        #
        # Apply facsimile transtating for signature requests
        #
        if template_use_facsimile:
            facsimile_tag_names = CustomFacsimileTagNames()
            rexp = r'<DIV\s+name="%s:([&#:|A-Za-z0-9._\-]*)">(.*?)</DIV>' % facsimile_tag_names[ 'name' ]
            r_facsimile = re.compile( rexp, re.I+re.DOTALL )
            matched = r_facsimile.search( text )

            ps = PortalInstance( self )
            source_url = ps['common'] or ps['portal']

            while matched:
                template_id = text[ matched.start(1) : matched.end(1) ]
                sign_area = text[ matched.start(2) : matched.end(2) ]
                signatures = self.hasTaskWithSignature( template_id ) or []
                n = 0

                for user_id, r_date, position in signatures:
                    member = membership.getMemberById( user_id )
                    if not member:
                        continue

                    user_briefname = member.getMemberBriefName()
                    user_lastname = member.getProperty('lname')

                    try: user_facsimile = member.getMemberFacsimile()
                    except: user_facsimile = None

                    if user_facsimile and ( sign_area.find(user_briefname) >= 0 or sign_area.find(user_lastname) >= 0 ):
                        if user_facsimile.find('/'+ps['instance']+'/') == 0:
                            user_facsimile = user_facsimile[len(ps['instance'])+1:]
                        elif user_facsimile.find('/docs/') == 0:
                            user_facsimile = user_facsimile[5:]

                        user_facsimile = joinpath( source_url, user_facsimile )
                        img = '<img src="' + user_facsimile + '" border=0>'
                        text = text[ :matched.start(0) ] + img + text[ matched.end(0): ]

                        if r_date and position:
                            rexp = r'<DIV\s+name="%s:%s"></DIV>' % ( facsimile_tag_names['date'], position )
                            r_facsimile_date = re.compile( rexp, re.I+re.DOTALL )
                            matched_date = r_facsimile_date.search( text )

                            if matched_date:
                                signature_date = '<font class=xxx>' + '%s.%s.%d' % ( r_date.dd(), r_date.mm(), r_date.year() ) + '</font>'
                                text = text[ :matched_date.start(0) ] + signature_date + text[ matched_date.end(0): ]

                        n = matched.start() + len(img)
                        break

                if n == 0:
                    n = matched.end()

                matched = r_facsimile.search( text, n )
        #
        # Remove empty (not defined) custom link comments, such as 'reply to' and another
        #
        if IsCustomDocument:
            text = TranslateCustomBody( text )

        if resolution is not None:
            display = resolution in ['block','none'] and resolution or None
            resolution_body = self.getDocumentResolution( display=display )
            if resolution_body:
                r_hint = re.compile( r'(<DIV\s*)([^>]*class=xxx\s*[^>]*)(>)', re.I+re.DOTALL )
                text = self.RunRESub( text, rfrom=r_hint, rto=r'\1\2 %s\3' % 'onclick="show_resolution(\'resolution_body\')"', mode=2 )
                text = '%s\n%s' % ( resolution_body, text )

        text = self.CheckSrcURL( text )

        if IsCustomDocument:
            text = self.ImplementLanguage( text )
            if _embedded_view_scripts:
                text = '%s\n%s' % ( _embedded_view_scripts, text )

        if not no_update and view:
            membership.updateLoginTime()
        return text

    def RunRESub( self, text, rfrom, rto, change_to='', mode=1 ):
        """
            Run regular expression sub function
        """
        if not text or not rfrom: return text

        if mode == 1:
            matched = rfrom.search( text )
            while matched:
                s = rto.sub( change_to, text[ matched.start() : matched.end() ] )
                text = text[ :matched.start() ] + s + text[ matched.end(): ]
                matched = rfrom.search( text, matched.end() + len(s) )
        elif mode == 2:
            try:
                text = rfrom.sub(rto, text)
            except:
                pass
        elif mode in [3, 5]:
            matched = rfrom.search( text )
            while matched:
                s = text[ matched.start(2) : matched.end(2) ]
                if mode == 3:
                    s = re.sub( r'<P[^>]*?>(?i)', rto, s )
                    s = re.sub( r'</P>(?i)', rto, s )
                elif mode == 5:
                    s = re.sub( r'<BR>(?i)', rto, s )
                text = text[ :matched.start(2) ] + s + text[ matched.end(2): ]
                matched = rfrom.search( text, matched.end() )
        elif mode == 4:
            r_hint = re.compile( r'Mso[&#:|A-Za-z0-9._\-]*', re.I+re.DOTALL )
            matched = rfrom.search( text )
            while matched:
                s = text[ matched.start(2) : matched.end(2) ]
                s = r_hint.sub(rto, s)
                text = text[ :matched.start(2) ] + s + text[ matched.end(2): ]
                matched = rfrom.search( text, matched.end() )

        return text

    def extra_cleaner( self, text=None ):
        """
            Apply extra clean actions for html-content.

            For documents which were embedded from MS Word replace tags containts 'Mso' specification.
            General action's call allocated in cleanup method.

            Result:

                String.
        """
        if not text: return ''

        r_body = re.compile( r'(<TABLE\s+)class=MsoTableGrid([^>]*>)', re.I+re.DOTALL )
        text = self.RunRESub( text, rfrom=r_body, rto=r'\1class=no_p\2', mode=2 )

        r_body = re.compile( r'(<TABLE\s+class=no_p[^>]*>)(.*?)(</TABLE>)', re.I+re.DOTALL )
        text = self.RunRESub( text, rfrom=r_body, rto=r'', mode=3 )

        r_body = re.compile( r'(<TD\s+class=no_p[^>]*>)(.*?)(</TD>)', re.I+re.DOTALL )
        text = self.RunRESub( text, rfrom=r_body, rto=r'', mode=3 )

        r_body = re.compile( r'(<TABLE\s+class=no_mso[^>]*>)(.*?)(</TABLE>)', re.I+re.DOTALL )
        text = self.RunRESub( text, rfrom=r_body, rto=r'xxx', mode=4 )

        r_body = re.compile( r'(<TD\s+class=no_mso[^>]*>)(.*?)(</TD>)', re.I+re.DOTALL )
        text = self.RunRESub( text, rfrom=r_body, rto=r'xxx', mode=4 )

        return text

    def CheckMacro( self, text=None, backward=None ):
        """
            Checks and translates macro definitions.

            Macro contents this command type: {express:$(option)}. Allowed the next keys: 'company'.

            Result:

                String.
        """
        if not text: return ''

        if backward is not None:
            try: option = self.getCategoryAttribute('$company')
            except: option = None
            if option is not None:
                rfrom = re.compile( r'%s-' % option )
                rto = r'{express:$company}'
                text = self.RunRESub( text, rfrom=rfrom, rto=rto, mode=2 )
        else:
            try: company = self.getCategoryAttribute('$company')
            except: company = None
            if company is not None:
                rfrom = re.compile(r'\{express:\$company\}')
                rto = r'%s-' % company
                text = self.RunRESub( text, rfrom=rfrom, rto=rto, mode=2 )

        return text

    def CheckSrcURL( self, text=None ):
        """
            Checks and translates portal src and href-links.

            Purpose of this action is to replace source URL for images and content-attachments inside the documents imported from another DB-instance, 
            for example, when documents transmitted to archive system.

            For system objects (images) such as logotypes and facsimile we tried to check src-attribute and replace it by way:

                - common-system specification (link to additional system containing /storage/system objects), and if it's not specified

                - current instance name (portal_url).

            For attachments allocated directly in the html-content, we replace object's absolute URL entirely.

            Result:

                String.
        """
        if not text: return ''

        ps = PortalInstance( self )
        source_url = ps['common'] or ps['portal']

        r_src = re.compile( r'([src|background]*=")http[^>]*?(/storage/system/[^>]*?")', re.I+re.DOTALL )
        matched = r_src.search( text )

        if matched:
            used_url = text[ matched.end(1) : matched.start(2) ]
            if source_url != used_url:
                text = r_src.sub( r'\1'+source_url+r'\2', text )

        obj_id = re.escape( self.getId() )
        obj_absolute_url = self.absolute_url()

        if obj_id and obj_absolute_url:
            r_href = re.compile( r'(href=")http[^>]*?/%s' % ( obj_id ), re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_href, rto=r'\1%s' % ( obj_absolute_url ), mode=2 )

        return text

    def isEditableBody( self ):
        """
            Returns the document editable body flag 1/0 if it exists
        """
        return 1
        body = self.EditableBody()
        if not body:
            return 0
        return len(body) > 0

    def EditableBody( self, view=None ):
        """
            Returns the document editable body.

            Arguments:

                'view' -- Boolean. This argument is passed to the _replaceLinks method.

            Result:

                String.
        """
        text = self._replaceLinks( Document.EditableBody( self ), types=None, view=view )
        IsCustomDocument = ObjectHasCustomCategory( self )

        if IsCustomDocument:
            text = self.CheckSrcURL( text )
            text = self.ImplementLanguage( text )
            if _embedded_edit_scripts:
                text = '%s\n%s' % ( _embedded_edit_scripts, text )

        return text

    def _replaceLinks( self, text, types=None, canonical=None, view=None ):
        """
            Renders special links in the given text.

            Arguments:

                'text'      -- String containing the document text.

                'types'     -- List of the processed link types. Link type can take
                               the value of either 'attach', 'this', field',
                               'portal' or 'site'. All types of links will be
                               processed in case the argument's value is None.

                'canonical' -- Boolean. Forces external links to be rendered in a
                               canonical way. See ItemBase.absolute_url for details.

                'view'      -- Indicates whether the document category attributes should
                               be rendered as text values or as input form fields.

            Currently supported link codes are: {express:field/<attribute_name>},
            {express:attach/<attachment_name} and {express:this}.

            Result:

                String.
        """
        if not text: return ''
        text = self.CheckMacro( text.strip() )

        REQUEST = aq_get( self, 'REQUEST', None )

        if not types:
            types = ( 'attach', 'this', 'field', 'portal', 'server', 'common', 'site', 'uid', )

        ps = PortalInstance( self )

        # XXX fix url tool (and portal and site objects) to use server_url
        if REQUEST is not None:
            urltool = getToolByName( self, 'portal_url' )
            portal_url = urltool()
        else:
            portal_url = aq_get( self, 'server_url', None, 1 )

        if canonical:
            relative_url = self.absolute_url( canonical=canonical )
            content_id = getContentId( self, extra=1 )
        else:
            relative_url = self.relative_url()

        if REQUEST is not None and REQUEST.get( 'ExternalPublish' ):
            external_url = portal_url
            # XXX must find real ids
            external_storage = 'storage'
            external_publisher = 'go'
        else:
            site = None
            external_url = site is not None and site.relative_url() or portal_url
            external_storage = external_publisher = None

        msg = getToolByName( self, 'msg', None )
        membership = getToolByName( self, 'portal_membership', None)
        catalog = getToolByName( self, 'portal_catalog', None )
        metadata = getToolByName( self, 'portal_metadata', None )

        try:
            category = metadata.getCategoryById( self.Category() )
        except:
            category = None

        AttributesRenderer = Cooker(view).__of__(self)
        sys_content = filter(lambda x: x.startswith('sysContent'), SYSTEM_FIELDS)
        ContentIsOpened = 0
        sys_followup = filter(lambda x: x.startswith('sysFollowup'), SYSTEM_FIELDS)
        FollowupIsOpened = 0

        regex = re.compile( r'\{?\bexpress:(\w+)\b/*([/?&=#$A-Za-z0-9._\-+%]*)\s*(style="[^"]+")?\}?' )
        match = regex.search( text )

        while match:
            option = match.group(1)
            subst = match.group(2)
            style = match.group(3) or ''

            if ( types and option not in types ) or not subst:
                subst = None

            elif option == 'attach':
                if canonical:
                    subst = "cid:" + content_id % subst
                else:
                    subst = joinpath( relative_url, subst )

            elif option == 'this':
                if not subst.startswith('#'):
                    subst = joinpath( relative_url, subst )

            elif option == 'field':
                name = subst
                state = None
                if name.find('.') > 0:
                    name, state = name.split('.')

                if name not in SYSTEM_FIELDS:
                    try:
                        value = self.getCategoryAttribute( name )
                        attr = category.getAttributeDefinition( name )
                        def_value = attr.getDefaultValue( default_only=1 )
                    except:
                        attr = MissingValue
                        value = def_value = None
                        subst = match.string[ match.start() : match.end() ] or ''
                else:
                    attr = MissingValue

                if attr is not MissingValue and not value and def_value:
                    value = def_value

                if attr is not MissingValue:
                    subst = AttributesRenderer.RenderAttribute( attr, value, style, param=state )
                else:
                    if name == 'sysRegNo':
                        #XXX it does not work if version is registered
                        subst = '<span name=%s>%s</span>' % ( \
                            name, ', '.join( self.getVersionable().registry_data.keys() ) )

                    elif name == 'sysRegDate':
                        #XXX it does not work if version is registered
                        archive = getClientStorageType( self )
                        document = self.getVersionable()
                        result = []

                        for rnum, reg_uids in document.registry_data.items():
                            for reg_uid in reg_uids:
                                registry = catalog.unrestrictedGetObjectByUid( reg_uid )
                                value = None
                                if registry is not None and 'creation_date' in registry.listColumnIds():
                                    entry = registry.getEntry( id=rnum )
                                    if entry is not None:
                                        value = entry.get('creation_date') #receipt_date
                                        result.append( '%s.%s.%d' % ( value.dd(), value.mm(), value.year() ) )
                                if archive and not value:
                                    try:
                                        value = self.registry_date
                                    except:
                                        value = self.creation_date
                                    result.append( '%s.%s.%d' % ( value.dd(), value.mm(), value.year() ) )
                        subst = '<span name=%s>%s</span>' % ( name, ', '.join( result ) )

                    elif name in ('sysDescr','sysDescription',):
                        description = escape( self.Description().strip(), 1 ).replace('\r', '').replace('\n', '<br>\n')
                        subst = '<span name=%s>%s</span>' % ( name, description )

                    elif name == 'sysCreator':
                        subst = '<span name=%s>%s</span>' % ( name, escape( membership.getMemberName( self.Creator() ) ) )

                    elif name == 'sysReplyTo':
                        portal_links = getToolByName( self, 'portal_links', None )
                        links = portal_links is not None and portal_links.getObjectLinks( self, 'from', 0, 1 ) or []
                        result = []
                        for x in links:
                            if x is None: continue
                            link = x.getObject()
                            if link is None: continue
                            destination = link.getDestinationObject()
                            result.append( destination.getInfoForLink( mode=4 ) )
                        to_ = result and msg('reply to')+'&nbsp;' or ''
                        subst = '<span name=%s>%s%s</span>' % ( name, to_, ', '.join(result) )

                    elif name == 'sysPrivate':
                        if IsPrivateObject( self ):
                            subst = '<span name=%s>%s</span>' % ( name, msg('confidentially') )
                        else:
                            subst = '<span name=%s></span>' % name

                    elif name in sys_content:
                        descriptions = None
                        if view:
                            brains_type = name[10:].lower() or None
                            if len(self.version._listVersions()) > 1:
                                version_id = self.getId()
                            else:
                                version_id = None

                            descriptions = self.followup.getFollowupDescriptions( recursive=1, \
                                check_delegation=1, version_id=version_id, state=state, \
                                brains_type=brains_type, \
                                )

                        if descriptions:
                            subst = ''
                            for x in descriptions:
                                x = re.sub(r'\n', '</p><p class=description>', x)
                                subst += '<p class=description>%s</p><br>' % x
                            subst = re.sub(r'<p class=description></p><br>', '', subst)
                            ContentIsOpened = 1
                        else:
                            subst = '<span name=%s%s></span>' % ( name, state and '.'+state or '' )

                    elif name in sys_followup:
                        responses = []
                        if view:
                            if name.endswith('WithNotifications'):
                                brains_type = name[11:-17].lower() or None
                                with_notifications = 1
                            else:
                                brains_type = name[11:].lower() or None
                                with_notifications = 0

                            if brains_type == 'request':
                                brains_type = [ 'request', 'inspection' ] #
                            elif brains_type:
                                brains_type = [ brains_type ]

                            if len(self.version._listVersions()) > 1:
                                version_id = self.getId() #getPrincipalVersionId()
                            else:
                                version_id = None

                            for x in brains_type:
                                r = self.followup.getResponseCollection( recursive=1, \
                                        with_notifications=with_notifications, \
                                        check_delegation=1, version_id=version_id, \
                                        no_sort=1, brains_type=x, \
                                        )
                                if r:
                                    responses.extend( r )

                        if responses:
                            subst = ''
                            responses.sort( lambda x, y: cmp(x['date'], y['date']) )

                            for response in responses:
                                try:
                                    r_date = response['date']
                                    if response.has_key('status'):
                                        if response.has_key('delegate'):
                                            r_member = response['delegate']
                                        else:
                                            r_member = membership.getMemberName(response['member']) or None
                                        if response['status'] in TaskCommits.TASK_INSPECTED_SUCCESSFULL:
                                            r_color = 'purple'
                                        elif response['status'] in TaskCommits.TASK_COMMITS_SUCCESSFULL:
                                            r_color = 'green'
                                        elif response['status'] in TaskCommits.TASK_COMMITS_FAILURE:
                                            r_color = 'red'
                                        else:
                                            r_color = 'black'
                                        r_status = '<font color=%s> [%s]</font>' % ( r_color, msg(response['status']) )
                                        r_to = ''
                                    elif with_notifications and response.has_key('rcpt'):
                                        r_member = membership.getMemberName(response['actor']) or None
                                        r_color = 'blue'
                                        r_status = '<font color=%s> [%s]</font>' % ( r_color, msg('notification') )
                                        r_to = '%s: ' % msg('Sent to users')
                                        len_rcpt = len(response['rcpt'])
                                        for n in range(len_rcpt):
                                            x = response['rcpt'][n]
                                            s = n < len_rcpt-1 and ',' or ''
                                            r_to += '%s%s ' % ( membership.getMemberBriefName(x,'LFM'), s )
                                    else:
                                        continue

                                    if r_member and r_date:
                                        subst += '<br><span style="font-size:11px;color:black"><b>%s</b>%s <b>%s</b></span>' % ( \
                                            r_date.strftime('%Y-%m-%d %H:%M'), r_status, r_member )
                                        if r_to:
                                            subst += '<br><span style="font-size:10px;"><b>%s</b></span>' % r_to
                                        r_text = str(response['text']).strip()
                                        is_plain_text = not r_text.startswith('<div class=comments>') and 1 or 0
                                        if r_text:
                                            if is_plain_text:
                                                r_text = re.sub( r'\n', '<br>', r_text )
                                            subst += '<br><span style="font-size:10px;">%s</span>' % r_text
                                        if is_plain_text:
                                            subst += '<br>'
                                        FollowupIsOpened = 1
                                except:
                                    continue
                        else:
                            subst = '<span name=%s></span>' % name

            elif option == 'portal':
                subst = joinpath( portal_url, subst )

            elif option == 'server':
                server_url = ps['portal'] or self.portal_url()
                subst = joinpath( server_url, subst )

            elif option == 'common':
                common_url = ps['common'] or ps['portal'] or self.portal_url()
                subst = joinpath( common_url, subst )

            elif option == 'site':
                if external_storage and subst.startswith( external_storage ):
                    subst = joinpath( external_url, external_publisher, subst[ len(external_storage): ] )
                else:
                    subst = joinpath( external_url, subst )

            elif option == 'uid':
                #split subst to uid itself and possibly version
                nd_uid = None
                version_id = None
                uid_data = subst.split('/')
                if len(uid_data) == 3 and uid_data[1] == 'version':
                    nd_uid = uid_data[0]
                    version_id = uid_data[2]
                elif len(uid_data) == 1:
                    nd_uid = subst
                if nd_uid:
                    obj_brains = catalog.unrestrictedSearch( nd_uid=nd_uid )
                    if obj_brains:
                        subst=obj_brains[0].getURL() + (version_id and '/version/%s' % version_id or '')

            if subst is None:
                match = regex.search( text, match.end() )
            else:
                text = text[ :match.start() ] + subst + text[ match.end(): ]
                match = regex.search( text, match.start() + len(subst) )

        if ContentIsOpened:
            r_hint = re.compile( r'(<TR\s*id=CONTENT[^>]*display:\s*)none([^>]*>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_hint, rto=r'\1block\2', mode=2 )

        if FollowupIsOpened:
            r_hint = re.compile( r'(<TR\s*id=FOLLOWUP[^>]*display:\s*)none([^>]*>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_hint, rto=r'\1block\2', mode=2 )

        del AttributesRenderer
        return text

    def ImplementLanguage( self, text, mode=None ):
        """
            Document content language support.
            This is an attempt to render <img> resources according to the document selected language.
        """
        lang_postfix = self.getLangPostfix()

        if lang_postfix:
            for ext in Config.FacsimileExtensions:
                if not mode or mode[0:3] == 'ins':
                    # Insertion language postfix
                    r_ext = re.compile( r'(src="http.*?/storage/system/[^\>]*)(%s)(")' % ext, re.I+re.DOTALL )
                    text = self.RunRESub( text, rfrom=r_ext, rto=r'\1-%s%s\3' % ( lang_postfix, ext ), mode=2 )
                else:
                    # Removal language postfix
                    r_ext = re.compile( r'(src="http.*?/storage/system/.*?)(-[^\-\/\>]*)(%s")' % ext, re.I+re.DOTALL )
                    text = self.RunRESub( text, rfrom=r_ext, rto=r'\1\3', mode=2 )

        try:
            msg_words = getToolByName( self, 'msg_words' )
            messages = getattr( msg_words, '_messages', None )
        except:
            messages = None

        if messages is not None and lang_postfix == 'en':
            for key in messages.keys():
                en = key
                ru = messages[key]['ru']
                if not mode or mode[0:3] == 'ins':
                    # Translate word in English
                    r_word = re.compile( r'([\>\.\,\;\s]+)(%s)([\<\.\,\&\s]+)' % ru, re.DOTALL )
                    text = self.RunRESub( text, rfrom=r_word, rto=r'\1%s\3' % ( en ), mode=2 )
                else:
                    # Translate word in Russian
                    r_word = re.compile( r'([\>\.\,\;\s]+)(%s)([\<\.\,\&\s]+)' % en, re.DOTALL )
                    text = self.RunRESub( text, rfrom=r_word, rto=r'\1%s\3' % ( ru ), mode=2 )

        return text

    def getLangPostfix( self, category=None ):
        """
            Returns current document <img> language postfix.
        """
        if category is None:
            metadata = getToolByName( self, 'portal_metadata' )
            try:
                category = metadata.getCategoryById( self.Category() )
            except:
                category = None

        if category is not None and category.getImplementLanguage():
            language = getattr( self, 'language', '' )
            default_language = getToolByName( self, 'msg' ).get_default_language()
            lang_postfix = language != default_language and language or ''
        else:
            lang_postfix = None

        return lang_postfix

    def _edit( self, text, *args, **kw ):
        """
            Changes the document text.

            The given text is being parsed so that all form input items
            which names match the document's category attributes ids are
            replaced with the "{express:field/<attribute_name>}" code. Each
            link containing the document's attachment url is replaced with
            "{express:attach/<attachment_name}" code. Finally, every url
            pointing to the document itself is replaced with the
            "{express:this}" string. _replaceLinks() method perfoms the
            backward convertion.

            Arguments:

                'text' -- New document text.

                '*args', '**kw' -- Additional arguments to be passed to Document._edit.
        """
        try:
            metadata = getToolByName( self, 'portal_metadata', None )
            category = metadata.getCategoryById( self.Category() )
        except:
            category = None

        # Regexp for searching element name
        r_sname = re.compile(r'name=(?:([\"\'])([A-Za-z0-9_$]*)\1|([A-Za-z0-9_]*))')         # simple name: name="xxx"
        r_dname = re.compile(r'name=(?:([\"\'])([A-Za-z0-9_$\.]*)\1|([A-Za-z0-9_\.]*))')     # dotted name: name="xxx.xxx"
        r_ename = re.compile(r'name=(?:([\"\'])([A-Za-z0-9_$\.\:]*)\1|([A-Za-z0-9_\.\:]*))') # extend name: name="xxx{.xxx}:xxx"
        r_value = re.compile(r'value=(?:([\"\'])(.*?)\1|([^\s>]+))')
        r_style = re.compile(r'style=".*?"')

        def getNameFromFragment( frag, r_name=r_sname ):
            match = r_name.search( frag )
            id = attr = param = name = None
            if match:
                name = match.group(1) in ['\'', '"'] and match.group(2) or match.group(3)
                if name.find('.') > 0:
                    id, attr = name.split('.')
                else:
                    id = name
                if attr and attr.find(':') > 0:
                    attr, param = attr.split(':')
                elif id.find(':') > 0:
                    id, param = id.split(':')
            return ( id, attr, param, name, )

        def getValueFromFragment( frag, r_value=r_value ):
            value = r_value.search( frag )
            if value:
                return value.group(1) in ['\'', '"'] and value.group(2) or value.group(3)
            return frag.find(' CHECKED') >= 0 and '1' or '' # For checkbox element

        def matchInput( frag, r_name=r_sname, value_only=None ):
            field_id, field_attr, field_param, name = getNameFromFragment( frag, r_name )

            value = getValueFromFragment( frag )
            
            if value_only:
                return ( field_id, field_attr, field_param, value )

            try:
                attr = category.getAttributeDefinition( field_id )
            except:
                attr = None

            subst = frag #leave non-category input fields

            if attr is not None:
                if attr.isMandatory() and not value:
                    #empty_mandatory_fields.append( field_id )
                    pass
                elif not attr.isReadOnly():
                    self.setCategoryAttribute( field_id, value, reindex=0 )

                x = r_style.search( frag )
                style = x and x.string[ x.start() : x.end() ] or ''

                if name:
                    subst = "{express:field/%s %s}" % ( name, style )

            elif name in SYSTEM_FIELDS:
                subst = "{express:field/%s }" % name

            return subst

        def matchTextarea( frag, r_name=r_sname, value_only=None ):
            field_id, field_attr, field_param, name = getNameFromFragment( frag, r_name )

            r_tag = re.compile('(?is)<TEXTAREA\s*?.*?>(.*?)</TEXTAREA>')
            match_tag = r_tag.search( frag )

            if match_tag is not None:
                value = match_tag.group(1)
            else:
                value = ''
            
            if value_only:
                return ( field_id, field_attr, field_param, value )

            try:
                attr = category.getAttributeDefinition( field_id )
            except:
                attr = None

            subst = frag #leave non-category input fields

            if attr is not None:
                if attr.isMandatory() and not value:
                    #empty_mandatory_fields.append( field_id )
                    pass
                elif not attr.isReadOnly():
                    self.setCategoryAttribute( field_id, value, reindex=0 )

                x = r_style.search( frag )
                style = x and x.string[ x.start() : x.end() ] or ''

                if name:
                    subst = "{express:field/%s %s}" % ( name, style )

            return subst

        def matchSelect( frag, r_name=r_sname, value_only=None ):
            field_id, field_attr, field_param, name = getNameFromFragment( frag, r_name )

            option_tags = re.findall( r'(?is)<OPTION[^>]*? selected.*?>', frag )

            value = []
            for option_tag in option_tags:
                v = r_value.search( option_tag )
                res = v.group(1) in ['\'', '"'] and v.group(2) or v.group(3)
                value.append( res )

            if len(value) == 1:
                value = value[0]
            elif not value:
                value = None

            x = r_style.search( frag )
            style = x and x.string[ x.start() : x.end() ] or ''

            dates = {}

            if field_id.endswith('_day') or field_id.endswith('_month') or field_id.endswith('_year'):
                dates[ field_id ] = value
                if field_id.endswith('_year'):
                    field_id = field_id[:-5]
                    if None not in dates.values():
                        value = parseDate( field_id, dates, default=None )
                    else:
                        value = None
                else:
                    value = MissingValue

            if value_only:
                return ( field_id, field_attr, field_param, value )

            if value is MissingValue:
                subst = ''
            else:
                if self.getCategory().getAttributeDefinition( field_id ).isMandatory() and not value:
                    #empty_mandatory_fields.append( field_id )
                    pass
                else:
                    self.setCategoryAttribute( field_id, value, reindex=0 )

                if name:
                    subst = "{express:field/%s %s}" % ( name, style )

            return subst

        def matchSpan( frag, r_name=r_dname ):
            field_id, field_attr, field_param, name = getNameFromFragment( frag, r_name )

            try:
                attr = category.getAttributeDefinition( field_id )
            except:
                attr = None

            subst = frag #leave non-category input fields

            if attr is not None:
                if attr.Type() == 'table' and not attr.isReadOnly():
                    style = ''
                    table_tag = re.compile('(?is)<TABLE\s*?.*?>(.*?)</TABLE>')
                    match_table_tag = table_tag.search( frag )

                    if match_table_tag:
                        table_body = match_table_tag.group(1)
                        values = matchTable( table_body, attr.getId() ) or []

                        x = self.getCategoryAttribute( field_id ) or {}
                        value = { 'count' : x.get('count') or len(values), 'values' : values }

                        self.setCategoryAttribute( field_id, value, reindex=0 )
                        CustomCookedTableNotifyOnChange( self, field_id )
                else:
                    x = r_style.search( frag )
                    style = x and x.string[ x.start() : x.end() ] or ''

                if name:
                    subst = "{express:field/%s %s}" % ( name, style )

            elif name in SYSTEM_FIELDS:
                subst = "{express:field/%s }" % name

            return subst

        def matchTable( table_body, attr_id ):
            tr_tag = re.compile('(?is)<TR\s*?.*?>(.*?)</TR>')
            td_tag = re.compile('(?is)<TD\s*?.*?>(.*?)</TD>')
            values = []

            tags = re.compile('(?is)<(INPUT|TEXTAREA|SELECT)\s*?(.*?)>')
            match_tr_tag = tr_tag.search( table_body )

            while match_tr_tag:
                tr_body = match_tr_tag.group(1)
                match_td_tag = td_tag.search( tr_body )
                IsValue = 0
                v = {}

                while match_td_tag:
                    td_body = match_td_tag.group(1)
                    match = tags.search( td_body )

                    if match:
                        tag = match.group(1).lower()
                        if tag == 'input':
                            x = matchInput( td_body, r_name=r_ename, value_only=1 )
                        elif tag == 'textarea':
                            x = matchTextarea( td_body, r_name=r_ename, value_only=1 )
                        elif tag == 'select':
                            x = matchSelect( td_body, r_name=r_ename, value_only=1 )
                        else:
                            x = None

                        if x:
                            id, attr, param, value = x
                            if id:
                                v[ attr or id ] = value
                                IsValue = 1

                    match_td_tag = td_tag.search( tr_body, match_td_tag.end() )

                if IsValue:
                    values.append( v )

                match_tr_tag = tr_tag.search( table_body, match_tr_tag.end() )

            return values
        #
        # Make all text parsing
        #
        if self._p_oid is not None:
            my_id = self.getId()

            # Step 1. Replacing all SPANs
            # ---------------------------
            r_tag = re.compile('(?is)(<SPAN .*?>.*?</SPAN>)')
            match_tag = r_tag.search( text )

            while match_tag:
                subst = matchSpan( match_tag.group(1) )
                text = text[ :match_tag.start() ] + subst + text[ match_tag.end(): ]
                match_tag = r_tag.search( text, match_tag.start() + len(subst) )

            # Step 2. Replacing all <INPUT... > fragments
            # -------------------------------------------
            r_tag = re.compile( r'(?is)<INPUT\b(.*?)>' )
            match_tag = r_tag.search( text )

            while match_tag:
                subst = matchInput( match_tag.group(1) )
                text = text[ :match_tag.start() ] + subst + text[ match_tag.end(): ]
                match_tag = r_tag.search( text, match_tag.start() + len(subst) )

            # Step 3. Replacing all <TEXTAREA ...>...</TEXTAREA> fragments
            # ------------------------------------------------------------
            r_tag = re.compile('(?is)(<TEXTAREA .*?>.*?</TEXTAREA>)')
            match_tag = r_tag.search( text )

            while match_tag:
                subst = matchTextarea( match_tag.group(1) )
                text = text[ :match_tag.start() ] + subst + text[ match_tag.end(): ]
                match_tag = r_tag.search( text, match_tag.start() + len(subst) )

            # Step 4. Replacing all <SELECT> lists
            # ------------------------------------
            r_tag = re.compile('(?is)(<SELECT .*?>.*?</SELECT>)')
            match_tag = r_tag.search( text )

            while match_tag:
                subst = matchSelect( match_tag.group(1) )
                text = text[ :match_tag.start() ] + subst + text[ match_tag.end(): ]
                match_tag = r_tag.search( text, match_tag.start() + len(subst) )

            # Step 5. Replacing relative links
            # --------------------------------
            attachments = [ id for id, ob in self.listAttachments() ]
            possible_urls = [ self.getVersion().absolute_url(), self.getVersionable().absolute_url(), \
                              self.getVersion().relative_url(), self.getVersionable().relative_url() ]
            self_urls = [ x for x in possible_urls if x ] # and x != '.' and len(x) > 2

            regex = re.compile( '(?:' + '|'.join( map(re.escape, self_urls) ) + ')' + \
                               r'(?:/+(([A-Za-z0-9,._\-+%]+)[/?&=#A-Za-z0-9._\-+%]*))'
                               )

            match = regex.search( text )

            while match:
                subst, id = match.groups()

                if id in attachments:
                    subst = joinpath('express:attach', subst)
                else:
                    subst = joinpath('express:this', subst)

                subst = subst.replace( '/document_frame?link=document_edit_form', '' )
                text = text[ :match.start() ] + subst + text[ match.end(): ]
                match = regex.search( text, match.start()+len(subst) )

            charset = getLanguageInfo( self.Language() )['http_charset']
            charmap = Config.CharsetEntityMap.get( charset )

            if charmap:
                # TODO: make utility filter
                for char, entity in charmap.items():
                    text = text.replace( char, entity )

            self._notifyOnDocumentChange()

        if category is not None:
            text = self.ImplementLanguage( text, mode='remove' )

        text = self.CheckMacro( text, 1 )

        Document._edit( self, text, *args, **kw )
        return text

    def cleanup( self, text=None, no_clean_html=0, using_fine_reader=0 ):
        """
            Removes redundant HTML tags and attributes from the document text.

            Arguments:

                'no_clean_html'     -- Boolean. Indicates whether the HTML source should be cleaned or not. In any case every
                                       reference to the document attachment will be converted into the relative url.

                'using_fine_reader' -- Boolean. If true, then use Fine Reader -
                                       specific parameters for cleanup.
        """
        if text is None:
            html = self.text
        else:
            html = text

        # Remove absolute links to attached files, make them relative
        rgx = re.compile( r'%s/' % ( self.absolute_url()) )
        html = re.sub( rgx, "" , html )

        # Remove <form></form> tag
        r_tag = re.compile('(?is)<FORM\s*?.*?>(.*?)</FORM>')
        match_tag = r_tag.search( html )
        if match_tag is not None:
            html = match_tag.group(1)

        member = getToolByName( self, 'portal_membership' ).getAuthenticatedMember()
        force = ( member is None or not member.IsAdmin() ) and 1 or 0

        if no_clean_html == 0 or force:
            # Cleanup Custom Document HTML
            if ObjectHasCustomCategory( self ):
                update_str = """
                    HTML HEAD TITLE
                    BODY
                    P class width align height style
                    NOBR class style
                    DIV class id name align
                    SPAN id name
                    A class id href name target style
                    STRONG BR B U I EM PRE STRIKE SUB SUP
                    H1 align valign class id style
                    H2 align valign class id style
                    H3 align valign class id style
                    H4 align valign class id style
                    H5 align valign class id style
                    H6 align valign class id style
                    UL class id
                    OL class id start
                    LI class id
                    TABLE align class id bgcolor width border cellspacing cellpadding bordercolor bordercolordark style
                    COLGROUP
                    COL style
                    TH class id bgcolor nowrap
                    TBODY class id
                    TR class id bgcolor valign align style
                    TD class id nowrap rowspan width height background bgcolor colspan valign align style
                    IMG style class id src width align height border hspace vspace alt
                    FONT size color class id face style
                    HR size style
                    INPUT class id name title style value size type disabled checked
                    TEXTAREA name title style rows cols
                    SELECT name title style size multiple
                    LABEL for
                    EM id class style title
                    """
            else:
                update_str = """
                    HTML HEAD TITLE
                    BODY
                    P class width align height style
                    DIV class id name align
                    SPAN id name style
                    A class id href name target
                    STRONG BR B U I EM PRE STRIKE SUB SUP
                    H1 align valign class id style
                    H2 align valign class id style
                    H3 align valign class id style
                    H4 align valign class id style
                    H5 align valign class id style
                    H6 align valign class id style
                    UL class id
                    OL class id start
                    LI class id
                    TABLE align class id bgcolor width border cellspacing cellpadding bordercolor bordercolordark style
                    COLGROUP
                    COL style
                    TH class id bgcolor nowrap
                    TBODY class id
                    TR class id bgcolor valign align style
                    TD class id nowrap rowspan width height background bgcolor colspan valign align style
                    IMG style class id src width align height border hspace vspace alt
                    FONT size color class id face style
                    HR size style
                    INPUT class id name title style value size type disabled checked
                    TEXTAREA name title style rows cols
                    SELECT name title style size multiple
                    LABEL for
                    """
            html = HTMLCleaner( html, update_str, 2, leave_str='BLOCKQUOTE STYLE', remove_str='SCRIPT' )
            html = self.extra_cleaner( html )

        elif using_fine_reader:
            #whole the tuning of cleanup goes here
            update_str = """
                    HTML HEAD TITLE
                    BODY
                    P class id width align height
                    DIV align
                    SPAN
                    A class id href name target
                    STRONG BR B U I EM PRE STRIKE SUB SUP
                    H1 align class id
                    H2 align class id
                    H3 align class id
                    H4 align class id
                    UL class id
                    OL class id start
                    LI class id
                    TABLE
                    TH
                    TBODY
                    TR
                    TD
                    IMG style class id src width align height border hspace vspace alt
                    FONT size color class id face
                    BLOCKQUOTE style
                    """
            html = HTMLCleaner( html, update_str, 0, leave_str='', remove_str='SCRIPT STYLE' )

        else:
            # Cleanup obligatory attributes
            html = HTMLCleaner( html, '', 0, leave_str='STYLE', remove_str='BLOCKQUOTE SCRIPT' )

        Document._edit( self, text=html )
        return html

    #security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'addFile' )
    def addFile( self, id=None, file=None, title=None, paste=None, try_to_associate=None, unresticted=None, \
                 REQUEST=None, **kw ):
        """
            Attach a file to the document
        """
        id = _addFile( self, id, file, title, REQUEST, unresticted=unresticted )
        basename, suffix = nt_splitext( id )

        #portal_info( 'HTMLDocument.addFile', '[%s] added %s="%s", %d bytes' % ( self.id, id, title, len(file) ) )
        new_file = self._getOb( id )

        #to work with versions:
        #self.attachments.append(id)

        if not self.cooked_text and  \
            hasattr(new_file, 'isTextual') and new_file.isTextual() and \
            try_to_associate is not None:
            #portal_info( 'HTMLDocument.addFile', '[%s] isTextual' % id )
            self.associateWithAttach( id )
        elif paste and not self.associated_with_attach:
            self.pasteFile( id )

        #portal_info( 'HTMLDocument.addFile', 'reindex %s' % `self` )
        self.reindexObject()
        return id

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'associateWithAttach' )
    def associateWithAttach( self, id ):
        """
            Set association with attachment file ONLY if we can convert file to html or text
        """
        self.failIfLocked()
        text = self[id].CookedBody( format='html' )

        #TODO: show message in readable format

        #except Exceptions.ConverterError:
        #    text = self.text
        #    raise ConverterError, "Failed to associate with attachment."

        self.associated_with_attach = id
        Document._edit( aq_parent(self), text=text )  # aq_parent(self) - is HTMLDocument
        #self.cleanup() - called by document_edit.py

        #portal_info( 'HTMLDocument.associateWithAttach', 'reindex %s' % `self` )
        self.reindexObject( idxs=['SearchableText'] )
        self._notifyOnDocumentChange()

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'removeAssociation' )
    def removeAssociation(self, id):
        """
            Remove association with attachment.
        """
        if self.associated_with_attach != id:
            return

        self.failIfLocked()

        self.associated_with_attach = None
        # clear the document text
        Document._edit( self, text='' )

        #portal_info( 'HTMLDocument.removeAssociation', 'reindex %s' % `self` )
        self.reindexObject( idxs=['SearchableText'] )
        self._notifyOnDocumentChange()

    #security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'pasteFile' )
    def pasteFile( self, id, size=None ):
        """
            Insert the file reference into the HTML code.
            Do not touch the file itself.

            Results:

                code -- return code: None - has not been applied, -1 - removed, 1 - inserted.
        """
        if not id:
            return None
        self.failIfLocked()

        ob = self._getOb( id )
        if ob is None:
            return None

        link = self.relative_url( action=id )
        title = escape(ob.title)

        addon = '<br><a class=attach href="express:attach/%s" target=_blank>%s</a>' % ( id, title )
        portal_log( self, 'HTMLDocument', 'pasteFile', 'link, addon, id', ( link, addon, id ) )

        html = self.text
        re_body = re.compile(r'(<SPAN name="sysAttachments">)(.*?)(</SPAN>)', re.DOTALL|re.I)
        body = re_body.search(html)

        if not body:
            if ObjectHasCustomCategory( self ):
                return -1
            html = html + addon
            code = 1
        else:
            links = html[ body.start(2) : body.end(2) ]
            portal_log( self, 'HTMLDocument', 'pasteFile', 'links', links )

            if links.find( id ) == -1:
                # insert link
                links += addon
                code = 1
            else:
                # if exists, remove it
                remove_re = re.compile(r'(<br><a[^>]*?%s[^>]*?>)[^>]*?(</a>)' % id, re.DOTALL|re.I)
                links = remove_re.sub('', links)
                code = -1

            html = html[ :body.end(1) ] + links + html[ body.start(3): ]
            html = self.check_attachments_visibility( html )

        self.edit( self.text_format, html )
        return code

    def check_attachments_visibility( self, html, clean=None ):
        attachment_tag_names = CustomAttachmentTagNames()
        rexp = r'<TR id=%s style="DISPLAY:(.*?)">' % attachment_tag_names[ 'id' ]
        attachre = re.compile( rexp, re.DOTALL|re.I )
        attach = attachre.search(html)
        if not attach:
            return html

        if clean:
            display = 'none'
            html = html[ :attach.start(1) ] + display + html[ attach.end(1): ]

        bodyre = re.compile(r'<SPAN name="sysAttachments">(.*?)</SPAN>', re.DOTALL|re.I)
        body = bodyre.search(html)
        if not body:
            return html

        if clean:
            html = html[ :body.start(1) ] + html[ body.end(1): ]
        else:
            display = html[ body.start(1) : body.end(1) ] and 'block' or 'none'
            html = html[ :attach.start(1) ] + display + html[ attach.end(1): ]

        return html

    #security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'removeFile' )
    def removeFile( self, id, is_notify=1 ):
        """
            Removes attached file from the document together with all references to the file from the document text.

            Arguments:

                'id' -- Attachment id.

            Result:

                Document source text.
        """
        if not id: return
        include_images = False

        self.failIfLocked()

        try: ob = self._getOb( id )
        except: ob = None
        html = self.text

        if include_images:
            if ob and ob.implements('isImage') or ob.meta_type in ( 'Image', 'Photo', ):
                # TODO: links to images with size (see above) are not stripped
                delre = re.compile('<img[^<>]+?src=[^<>]*?%s.*?>(<br>)?' % id, re.I|re.DOTALL)
        else:
            delre = re.compile('(<br>)?<a([^<>]+?)href=([^<>]*?)%s(.*?)>(.*?)</a>' % id, re.I|re.DOTALL)

        if include_images:
            if ob and ob.implements('isImage') and callable(getattr(ob, 'isTIFF')) and ob.isTIFF():
                if ob.getFramesNumber() > 1:
                    delre = re.compile(r'<span[^<>]*>\s*<a[^<>]+?href=[^<>]*?%s\W+[^<>]*>\s*<img[^<>]+?src=[^<>]*?%s\W+.*?</span>\s*(?:<br>)*' % (id, id), re.I|re.DOTALL)
                else:
                    delre = re.compile('<img[^<>]+?src=[^<>]*?%s\W+.*?>(<br>)?' % id, re.I|re.DOTALL)

        html = delre.sub('', html)
        html = self.check_attachments_visibility( html )

        #self.attachments.remove(id)

        #for version in self.version._listVersions():
        #    if id in version.attachments:
        #        break
        #else:
        #    self.manage_delObjects( id )
        self.manage_delObjects( id )

        if self.associated_with_attach == id:
            self.associated_with_attach = None

        Document._edit( aq_parent(self), text=html )  # aq_parent(self) is HTMLDocument

        if is_notify:
            self._notifyOnDocumentChange()
            #portal_info( 'HTMLDocument.removeFile', 'reindex %s' % `self` )
            self.reindexObject()
            return html

        return
    #
    #   Containment events handlers ==============================================================================
    #
    def _check_containment( self, mode=None ):
        """
            Checks either document exists in the catalog
        """
        portal_catalog = getToolByName( self, 'portal_catalog', None )
        if portal_catalog is None:
            return None

        res = []
        id = self.getId()

        try:
            if id:
                res = portal_catalog.unrestrictedSearch( id=id )
            IsFound = res and len(res) or -1
        except:
            portal_error( 'HTMLDocument._check_containment', 'search error, id: %s' % id, exc_info=True )
            IsFound = None

        if IsFound > 1:
            portal_error( 'HTMLDocument._check_containment', 'found more that one item, id: %s [%s]' % ( id, IsFound ) )
            IsFound = None

        return IsFound

    def _containment_onAdd( self, item, container ):
        """
            Add callback
        """
        #if aq_base(container) is aq_base(self):
        #    return
        #IsFound = self._check_containment('add')
        #if IsFound is None or IsFound == 1:
        #    return
        #portal_log( self, 'HTMLDocument', '_containment_onAdd', 'IsFound', IsFound )
        portal_log( self, 'HTMLDocument', '_containment_onAdd', 'self, item, container', (`self`, `item`, `container`) )
        ObjectManager.manage_afterAdd( self, item, container )
        self.addUid( item )
        Document.manage_afterAdd( self, item, container )

        # XXX fix permissions for versionable
        for perm in self._versionable_perms:
            delattr( self, perm )
    #
    #   Instance events handlers =================================================================================
    #
    def _instance_onClone( self, source, item ):
        """
            Copy callback
        """
        portal_log( self, 'HTMLDocument', '_instance_onClone', 'uid [item, source]', ( item.getUid(), source.getUid() ) )

        member = _getAuthenticatedUser(self)
        membership = getToolByName( self, 'portal_membership' )
        copy_clipboard = member is None and 1 or membership.getInterfacePreferences('copy_clipboard')

        # TODO move this to link tool
        # create links from this document
        # according links from the document, clone of which we are
        links = getToolByName( self, 'portal_links', None )
        try:
            cloned_links = links.searchLinks( source_uid=source.getUid() )
        except:
            cloned_links = []
        #XXX Only links to the existing documents are copied here.
        for x in cloned_links:
            relation = x.relation_type * 2 + x.relation_direction
            #do not copy 'Document depends on current' links
            if relation:
                try:
                    links.createLink( source_uid=self.getUid(), destination_uid=x.dest_uid, relation=relation )
                except ( ValueError, KeyError ):
                    pass

        owner = item.getOwner()
        if owner is not None:
            self.changeOwnership( owner.getUserName() )

        if hasattr( aq_base(self), 'registry_data' ):
            #for backward compatibility:
            try: del self.registry_id
            except: pass

            self.registry_data = {}
            #portal_info( 'HTMLDocument._instance_onClone', 'reindex %s' % `self` )
            self.reindexObject( idxs=['registry_ids',] )

        if hasattr( aq_base(self), 'talkback' ):
            self.talkback = DiscussionItemContainer()

        # Remove all attachments in case creator has not property 'copy_clipboard'
        if not copy_clipboard:
            for id, ob in self.listAttachments():
                self.removeFile( id )

        ObjectManager.manage_afterClone( self, item )
        Document.manage_afterClone( self, item )

    def _instance_onDestroy( self ):
        """
            Destroy callback
        """
        return
    #
    #   Notification events handlers =============================================================================
    #
    def _notifyAttachChanged( self, id ):
        """
            Notifies document that particular attachment file was changed.

            Arguments:

                'id' -- Attachment file id.

            In case the attachment file is associated with the document's editable
            version, file contents will be converted and inserted into the
            version text.
        """
        if self.associated_with_attach == id:
            #this is textual document
            #try to convert document text to html
            try:
                text = self[ id ].CookedBody( format='html' )
            except Exceptions.ConverterError:
                text = self.cooked_text

            Document._edit( self, text=self.cleanup() )

            portal_info( 'HTMLDocument._notifyAttachChanged', 'associated_with_attach id: %s, self: %s' % ( \
                id, `self` ) \
                )
            self.reindexObject( idxs=['SearchableText'] )
            self._notifyOnDocumentChange()

    def _notifyOfCopyTo( self, container, op=0 ):
        """
            Pre-copy/move operation notification.

            Arguments:

                'container' -- Object container.

                'op' -- Operation type indicator. Can take the value of either
                        1 for the move operation or 0 for the copy
                        operation.
        """
        if op == 1: # move operation
            self.failIfLocked()

    security.declarePrivate( '_notifyOnDocumentChange' )
    def _notifyOnDocumentChange( self ):
        """
            Notifies that document was changed
        """
        pass

    def notifyWorkflowCreated( self ):
        """
            Notifies the workflow that *self* was just created
        """
        Document.notifyWorkflowCreated( self )
        #portal_info( 'HTMLDocument.notifyWorkflowCreated', 'reindex %s' % `self` )
        self.reindexObject( idxs=['state'] )

    def notifyWorkflowStateChanged( self ):
        """
            Notifies that the *self* workflow state was changed
        """
        if not self.registry_ids():
            return

        for rnum, reg_uids in self.registry_data.items():
            for reg_uid in reg_uids:
                registry = getObjectByUid( self, reg_uid )
                if registry is None:
                    portal_error( 'HTMLDocument.notifyWorkflowStateChanged', 'not registry %s' % reg_uid )
                    continue
                if not registry._catalog.indexes.has_key('RecordState'):
                    portal_info( 'HTMLDocument.notifyWorkflowStateChanged', 'not index %s' % reg_uid )
                    continue
                entry = registry.getEntry( rnum )
                if entry is None:
                    portal_info( 'HTMLDocument.notifyWorkflowStateChanged', 'not entry %s, %s' % ( rnum, reg_uid ) )
                    continue

                portal_log( self, 'HTMLDocument', 'notifyWorkflowStateChanged', 'entry', rnum )
                try:
                    entry.reindex( idxs=['RecordState'] )
                except:
                    portal_error( 'HTMLDocument.notifyWorkflowStateChanged', 'reindex error: %s, registry: %s' % ( \
                        rnum, reg_uid ) \
                        )
    #
    #   ==========================================================================================================
    #
    def objectIds( self, spec=None ):
        # It's allowed to pass sequence type 'spec' list, such as: ( 'Image Attachment', 'File Attachment', )
        if not spec:
            ids = ObjectManager.objectIds(self)
            followup = ( hasattr( aq_base( self ), 'followup' ) and self.followup or None )
            if followup is not None:
                ids.append('followup')
        else:
            if type(spec) == type(''):
                spec = [spec]
            ids = []
            for x in spec:
                ids.extend( ObjectManager.objectIds(self, x) )
        return ids

    def getAttachmentsInfo( self ):
        """
            Returns attachments info as String
        """
        info = ''
        try:
            for id, file in self.listAttachments():
                if info: info += ' '
                basename, extension = nt_splitext( id )
                while extension and extension[0]=='.':
                    extension = extension[1:]
                info += '%s %s' % ( file.Title(), extension )
        except: pass
        return info

    security.declareProtected( CMFCorePermissions.View, 'listAttachments' )
    def listAttachments( self, no_inline=False, no_emailed=False ):
        """
            Returns a list of the document's file attachments.

            Result:

                List of (id, attachment) pairs.
        """
        items = []
        for x in self.objectItems():
            if x[0] in ('followup', 'version'):
                continue
            if getattr(x[1], 'meta_type', None) not in Config.AttachmentTypes:
                continue
            if not _checkPermission( CMFCorePermissions.View, x[1] ):
                continue
            items.append( x )

        if no_inline:
            content_id = getContentId( self, extra=1 )
            text = self.FormattedBody( canonical=True )
            files = []
            for id, file in items:
                cid = content_id % id
                inline = bool( text.count( cid ) )
                if not inline:
                    files.append(( id, file ))

        elif no_emailed:
            files = []
            for id, file in items:
                basename, suffix = nt_splitext( id )
                if suffix not in Config.NoEmailedExtensions:
                    files.append(( id, file ))

        else:
            files = items

        return files

    def getAttachmentsList( self ):
        """
            Returns list of all attachments.

            Result:

                List of (id, attachment url) pairs.
        """
        files = []
        for id, attach in self.listAttachments():
            files.append(( id, attach.relative_url() ))
        return files

    def getContentsSize( self ):
        """
            Returns total size of the document text and all attachments.

            Result:

                Integer. Size in bytes.
        """
        size = len( self.text or '' )
        for id, attach in self.listAttachments():
            size += attach.get_size()
        return size

    security.declareProtected( CMFCorePermissions.View, 'lockViewAttachment' )
    def lockViewAttachment( self, id ):
        """
            Locks view permission to the given attachment.

            Arguments:

                'id' -- Attachment file id.
        """
        ob = self[ id ]
        if ob is None:
            return
        ob.manage_permission( CMFCorePermissions.View, ( Roles.Manager, Roles.Owner, Roles.Editor, Roles.Writer, ), 0 )
        ob.reindexObject( idxs=['allowedRolesAndUsers'] )    

    security.declareProtected( CMFCorePermissions.View, 'unlockViewAttachment' )
    def unlockViewAttachment( self, id ):
        """
            Unlocks view permission to the given attachment.

            Arguments:

                'id' -- Attachment file id.
        """
        ob = self[ id ]
        if ob is None:
            return
        ob.manage_permission( CMFCorePermissions.View, ( Roles.Manager, Roles.Owner, Roles.Editor, Roles.Writer, Roles.Reader, Roles.Author, ), 0 )
        ob.reindexObject( idxs=['allowedRolesAndUsers'] )    

    #security.declareProtected( CMFCorePermissions.View, 'getLockCreator' )
    def getLockCreator( self, lock=None ):
        """
            Returns username of the lock creator, or None.
        """
        if lock is None:
            lock = self.wl_lockValues( killinvalids=1 )
            lock = lock and lock[0] or None

        return lock and lock.getCreator()[1]

    #security.declareProtected( CMFCorePermissions.View, 'isLocked' )
    def isLocked( self ):
        """
            Checks whether the object is locked by _another_ user.
        """
        if not self.wl_isLocked():
            return 0

        return ( _getAuthenticatedUser(self).getUserName() != self.getLockCreator() )

    #security.declareProtected( CMFCorePermissions.View, 'isLockPermitted' )
    def isLockPermitted( self ):
        """
            Checks whether the current user can lock or unlock the object.
        """
        return not self.isLocked() or _checkPermission( CMFCorePermissions.ManagePortal, self )

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'lockDocument' )
    def lockDocument( self ):
        """
            Locks the object.
        """
        self.failIfLocked()
        if self.wl_isLocked():
            return

        metadata = getToolByName( self, 'portal_metadata', None )
        timeout = metadata is not None and metadata.getCategoryById(self.category).getLockTimeout() or 300
        lock = LockItem( creator=_getAuthenticatedUser(self), timeout='Seconds-%d' % timeout )

        self.wl_setLock( locktoken=lock.getLockToken(), lock=lock )

    security.declareProtected( CMFCorePermissions.View, 'unlockDocument' )
    def unlockDocument( self ):
        """
            Unlocks the object.
        """
        if not self.isLockPermitted():
            raise Exceptions.Unauthorized( "You have no permission to unlock this object." )

        self.wl_clearLocks()

    security.declarePublic( 'failIfLocked' )
    def failIfLocked( self ):
        """
            Raises an exception if the object is locked by _another_ user.
        """
        try:
            SimpleAppItem.failIfLocked( self )
        except Exceptions.ResourceLockedError:
            if _getAuthenticatedUser( self ).getUserName() != self.getLockCreator():
                raise

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'setFormat' )
    def setFormat( self, format ):
        """
            Set Dublin Core Format element - resource format
        """
        self.format = format or default_content_type

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'PUT' )
    def PUT( self, REQUEST, RESPONSE ):
        """
            Handle HTTP (and presumably FTP?) PUT requests
        """
        # TODO fix characters in REQUEST.BODY
        body = REQUEST.get('BODY', '')
        guessedformat = REQUEST.get_header('Content-Type') or default_content_type
        ishtml = (guessedformat == 'text/html') or html_headcheck(body)

        if ishtml: self.setFormat('text/html')
        else: self.setFormat('text/plain')

        body = HTMLCleaner(body)

        try:
            headers, body, format = self.handleText( text=body )
            safety_belt = headers.get('SafetyBelt', '')
            self.setMetadata(headers)
            self._edit(text=body, safety_belt=safety_belt)
        except 'EditingConflict', msg:
            # XXX Can we get an error msg through?  Should we be raising an
            #     exception, to be handled in the FTP mechanism?  Inquiring
            #     minds...
            get_transaction().abort()
            RESPONSE.setStatus(450)
            return RESPONSE
        except Exceptions.ResourceLockedError, msg:
            get_transaction().abort()
            RESPONSE.setStatus(423)
            return RESPONSE

        RESPONSE.setStatus(204)
        #portal_info( 'HTMLDocument.PUT', 'reindex %s' % `self` )
        self.reindexObject()
        return RESPONSE

    security.declarePublic('getWorkflowState')
    def getWorkflowState( self ):
        """
            Returns the object workflow state
        """
        workflow = getToolByName( self, 'portal_workflow', None )
        if workflow is None:
            return None
        return workflow.getInfoFor( self, 'state', None )

    security.declarePublic('registry_ids')
    def registry_ids( self ):
        """
            Used by catalog
        """
        return getattr(self, 'registry_data', {}).keys()

    security.declarePublic('registry_numbers')
    def registry_numbers( self, delimeter='/', min_length=3, original=1 ):
        """
            Returns registry numbers string, such as: 2-01/1 -> 2-01 001 specially for FULLTEXT searching
        """
        s = ''
        registry_ids = self.registry_ids()
        for key in registry_ids:
            if s: s += ' '
            s += ' '.join([len(x) < min_length and ('00000%s' % x)[-min_length:] or x for x in key.split(delimeter)])
        if original:
            s += ' '+' '.join(registry_ids)
        return s

    security.declarePublic('isAnyRegistryVisible')
    def isAnyRegistryVisible( self ):
        """
            Check any registries visible for given document (restricted)
        """
        accessible = False
        for rnum, reg_uids in self.registry_data.items():
            for reg_uid in reg_uids:
                registry = getObjectByUid( self, reg_uid, restricted=1 )
                if registry is not None:
                    accessible = True
                    break
            if accessible: break
        return accessible
    #
    # Distribution interface methods ================================================================================
    #
    security.declarePublic( 'distributeDocument' )
    def distributeDocument( self, template, transport, mto=None, mfrom=None, subject=None, from_member=None, \
            namespace=None, REQUEST=None, lang=None, raise_exc=None, letter_parts=[], \
            fax_numbers=None, **kw ):
        """
            Distribute document:
                letter_content - is array with values of what to distribute (see 'skins/distribute_document_form.dtml')

            in self.distribution_log are stored log about document's distribution
        """
        skins = getToolByName( self, 'portal_skins', None )
        mail = getToolByName( self, 'MailHost', None )
        msg_catalog = getToolByName( self, 'msg', None )
        if None in ( skins, mail, ):
            return 0

        source_link = self.locate_url() #self.absolute_url(canonical=1)
        source_title = self.Title()
        ps = PortalInstance( self )
        common_url = ps['common']
        portal_url = ps['portal']

        mto_ids = parseMemberIDList( self, mto )

        email_envelope = mail.createMessage( multipart=1 )
        fax_envelope = mail.createMessage( multipart=1 )
        fmt = 'text/html' # self.Format()

        document_attachment_list = []
        attachments_ids = REQUEST.get( 'attachments' )

        if 'attachment' in letter_parts and attachments_ids:
            for id in attachments_ids:
                file = self.getVersion()._getOb( id )
                ctype = file.getContentType()
                fname = file.getProperty('filename') or file.getId()
                basename, suffix = nt_splitext( fname )
                if suffix in Config.NoEmailedExtensions:
                    continue
                item = MailMessage( ctype or Config.DefaultAttachmentType )
                item.set_payload( file.RawBody() )
                IsAdded = 0

                if 'email' in transport:
                    email_envelope.attach( item, filename=fname )
                    IsAdded = 1

                if 'fax' in transport:
                    basename, suffix = nt_splitext( fname )
                    suffix = suffix.lower()
                    if suffix in Config.FaxableExtensions:
                        fax_envelope.attach( item, filename=fname )
                        IsAdded = 1

                if IsAdded:
                    document_attachment_list.append( fname )

        metadata_name = '%s.%s' % ( msg_catalog is not None and msg_catalog('Metadata HTML') or 'metadata', 'mht' )
        letter_name = '%s.%s' % ( source_title or msg_catalog is not None and msg_catalog('Letter HTML') or 'letter', 'mht' )

        # locales for dtml
        letter_attachments_types = {
              'body' : {'en':'document text (%s)' % 'letter.mht', 'ru':'Document text (%s)' % letter_name},
              'attachment' : {'en':'Document attachments', 'ru':'Document attachments'},
              'metadata' : {'en':'Metadata (%s)' % 'metadata.mht', 'ru':'Metadata (%s)' % metadata_name}
        }

        content_id = getContentId( self, extra=1 )
        if 'body' in letter_parts:
            #Document body
            msg = mail.createMessage( fmt, multipart='related', charset=mail.getOutputCharset( self.Language() ) )
            text = self.FormattedBody( html=True, width=76, canonical=True )
            if common_url != portal_url:
                text = text.replace( common_url, portal_url )

            # Remove break in header part of template
            r_hint = re.compile( r'(<body[^>]*>\s+)(<BR>)(\s+<STYLE[^>]*>)', re.I+re.DOTALL )
            text = self.RunRESub( text, rfrom=r_hint, rto=r'\1\3', mode=2 )

            allowed_extensions = uniqueValues(Config.ImageExtensions)
            # Config.FaxableExtensions, these types are not allowed because we can not add it to mht-format.
            # But if we know that such of them added to attaches we should show file's attachment title

            for id, file in self.listAttachments():
                fname = file.getProperty( 'filename' ) or file.getId()
                basename, suffix = nt_splitext( fname )
                suffix = suffix.lower()
                if suffix not in allowed_extensions:
                    delre = re.compile('(<br>)?<a([^<>]+?)href=([^<>]*?)%s(.*?)>(.*?)</a>' % id, re.I|re.DOTALL)
                    if not delre.search( text ):
                        continue
                    if fname in document_attachment_list:
                        text = self.RunRESub( text, rfrom=delre, rto=r'\1\5', mode=2 )
                    else:
                        text = self.RunRESub( text, rfrom=delre, rto=r'', mode=2 )

            text = self.check_attachments_visibility( text )

            item = mail.createMessage( fmt )
            item.set_payload( text )
            msg.set_payload( [] )
            msg.attach( item, location=self.absolute_url() )

            mht = mail.createMessage( Config.DefaultAttachmentType ) # 'message/rfc822'
            mht.set_param( 'name', letter_name )

            for id, file in self.listAttachments():
                cid = content_id % id
                inline = bool( text.count( cid ) )
                if not inline:
                    continue

                fname = file.getProperty( 'filename' ) or file.getId()
                basename, suffix = nt_splitext( fname )
                suffix = suffix.lower()
                if suffix not in Config.ImageExtensions:
                    continue

                ctype = file.getContentType()
                item = mail.createMessage( ctype or Config.DefaultAttachmentType )
                item.set_payload( file.RawBody() )
                msg.attach( item, filename=fname, cid=cid )

            r_tag = re.compile(r'(?si)<IMG .*?>')
            r_src = re.compile(r'(?si)src=(?:([\"\'])(.*?)\1|(.*?))')
            match_tag = r_tag.search( text )

            def getSrcFromFragment( frag, r_src=r_src ):
                src = r_src.search( frag )
                if src:
                    return src.group(1) in ['\'', '"'] and src.group(2) or src.group(3)
                return None

            def attachFromSrc( self, mail, src, msg ):
                path = src and urlparse( src )[2]
                if not path:
                    return

                file = self.unrestrictedTraverse( path, None )
                if file is None or not isinstance( file, ImageAttachment ):
                    return

                fname = file.getProperty( 'filename' ) or file.getId()
                basename, suffix = nt_splitext( fname )
                suffix = suffix.lower()
                if suffix not in Config.ImageExtensions:
                    return

                ctype = file.getContentType()
                item = mail.createMessage( ctype or Config.DefaultAttachmentType )

                item.set_payload( file.RawBody() )
                msg.attach( item, filename=fname, location=src )

            processed_urls = []
            while match_tag:
                frag = text[ match_tag.start() : match_tag.end() ]
                src = getSrcFromFragment( frag )
                if src not in processed_urls:
                    processed_urls.append( src )
                    attachFromSrc( self, mail, src, msg )
                match_tag = r_tag.search( text, match_tag.end() )

            msg.add_header( 'Subject', letter_name )
            msg.add_header( 'From', "<Express Suite DMS>" )
            msg.set_param( 'type', fmt )

            mht.set_payload( str(msg) )
            for envelope in  [ fax_envelope, email_envelope ]:
                envelope.attach( mht, filename=letter_name )

        if 'metadata' in letter_parts:
            #Metadata
            msg = mail.createMessage( 'text/html', multipart='related', charset=mail.getOutputCharset( self.Language() ) ) # 'message/rfc822'
            mht = mail.createMessage( Config.DefaultAttachmentType )
            mht.set_param( 'name', metadata_name )

            try:
                metadata_template = getattr( aq_base( skins['mail_templates'] ), 'metadata_template' )
            except AttributeError:
                raise KeyError, template

            metadata = metadata_template( self, namespace or REQUEST, lang=lang, charset=getLanguageInfo( lang )['http_charset'], **kw )
            body = msg.get_body()
            body.set_payload( metadata )

            instance = aq_get( self, 'instance', None, 1 ) or 'docs'
            default_logo = CustomDefaultLogo()
            file = self.unrestrictedTraverse( '/%s%s' % ( instance, default_logo ), None )
            if file:
                ctype = file.getContentType()
                fname = file.getProperty('filename') or file.getId()
                item = mail.createMessage( ctype or Config.DefaultAttachmentType  )
                item.set_payload( file.RawBody() )
                msg.attach( item, inline=1, filename=fname, location=self.portal_url() + default_logo )

            msg.add_header( 'Subject', letter_name )
            msg.add_header( 'From', "<ExpressSuiteDMS>" )
            msg.set_param( 'type', fmt )
        
            mht.set_payload( str(msg) )
            for envelope in [ fax_envelope, email_envelope ]:
                envelope.attach( mht, filename=metadata_name )

        # store event to log
        ts = str(int(DateTime()))
        membership = getToolByName( self, 'portal_membership', None )
        member = membership.getAuthenticatedMember()
        who_id = member.getId()
        log_id = len(self.distribution_log)
        count = 0

        if 'email' in transport:
            try:
                letter_template = getattr( aq_base( skins['mail_templates'] ), template )
            except AttributeError:
                raise KeyError, template

            mto_authorised = []
            mto_not_authorised = []

            if 'link_to_doc' in letter_parts:
                allowed_users = membership.listAllowedUsers( self, roles=[Roles.Editor, Roles.Writer, Roles.Reader] ) or []
                allowed_users.extend( membership.listAllowedUsers( self, roles=[Roles.Author], local_only=1 ) )
                for x in mto_ids:
                    user = membership.getMemberById( x )
                    if user is not None:
                        if user.getUserName() in allowed_users or self.Creator() == x or user.IsManager():
                            mto_authorised.append( x )
                        else:
                            mto_not_authorised.append( x )
                    elif x.find('@') > 0:
                        mto_not_authorised.append( x )
            else:
                mto_not_authorised = mto_ids

            attributes = {}
            IsReturnReceiptTo = kw and kw.has_key('return_receipt_to') and kw['return_receipt_to'] and 1 or 0
            if IsReturnReceiptTo:
                attributes['return_receipt_to'] = 1
            IsConfirmReadingTo = kw and kw.has_key('confirm_reading_to') and kw['confirm_reading_to'] and 1 or 0
            if IsConfirmReadingTo:
                attributes['confirm_reading_to'] = 1

            if mto_authorised:
                text = letter_template( aq_parent( self ), namespace or REQUEST, lang=lang,
                                        letter_attachments_types=letter_attachments_types,
                                        document_attachment_list=document_attachment_list,
                                        source_link=source_link,
                                        letter_parts=letter_parts,
                                        **kw
                                      )
                email_envelope.get_body().from_text( text )
                count += self.MailHost.send( email_envelope, mto=mto_authorised, mfrom=mfrom, subject=subject, \
                                             from_member=from_member, IsReturnReceiptTo=IsReturnReceiptTo, \
                                             IsConfirmReadingTo=IsConfirmReadingTo, \
                                             object_url=self.physical_path(), \
                                             raise_exc=raise_exc )
            if mto_not_authorised:
                text = letter_template( aq_parent( self ), namespace or REQUEST, lang=lang,
                                        letter_attachments_types=letter_attachments_types,
                                        document_attachment_list=document_attachment_list,
                                        source_link=source_link,
                                        letter_parts=[],
                                        **kw
                                      )
                email_envelope.get_body().from_text( text )
                count += self.MailHost.send( email_envelope, mto=mto_not_authorised, mfrom=mfrom, subject=subject, \
                                             from_member=from_member, IsReturnReceiptTo=IsReturnReceiptTo, \
                                             IsConfirmReadingTo=IsConfirmReadingTo, \
                                             object_url=self.physical_path(), \
                                             raise_exc=raise_exc )

            self.distribution_log.append( { 
                                        'date'       : ts
                                      , 'message'    : email_envelope
                                      , 'subject'    : subject
                                      , 'who_id'     : who_id
                                      , 'who_fio'    : {'lname': member.getProperty('lname'), 'fname': member.getProperty('fname'),'mname': member.getProperty('mname')}
                                      , 'recipients' : membership.listSortedUserNames( ids=mto, contents='id' )
                                      , 'log_id'     : log_id
                                      , 'count'      : count
                                      , 'attributes' : attributes
                                      } )

            if count:
                portal_info( 'HTMLDocument.distributeDocument', 'sent by email: who_id %s, count %s' % ( who_id, count ) )

        if 'fax' in transport and fax_numbers:
            #subject = '[FAX:%s]' % fax_numbers[0]
            #fax_from = CustomFaxEmail()
            fax_addresses = [ '%s@faxmaker.com'.replace( ' ', '' ) % x for x in fax_numbers ]
            fax_from = CustomFaxEmail()
            count = self.MailHost.send( fax_envelope, mto=fax_addresses, mfrom=fax_from, subject=subject, \
                                        from_member=from_member, \
                                        object_url=self.physical_path(), \
                                        raise_exc=raise_exc )

            self.distribution_log.append( { 
                                        'date'       : ts
                                      , 'message'    : fax_envelope
                                      , 'subject'    : subject
                                      , 'who_id'     : who_id
                                      , 'who_fio'    : {'lname': member.getProperty('lname'), 'fname': member.getProperty('fname'),'mname': member.getProperty('mname')}
                                      , 'recipients' : fax_addresses
                                      , 'log_id'     : log_id
                                      , 'count'      : count
                                      } )

            if count:
                portal_info( 'HTMLDocument.distributeDocument', 'sent by fax: who_id %s, count %s' % ( who_id, count ) )

        self._p_changed = 1
        return count

    security.declarePublic( 'receiveMailCopyFromDistributionLog' )
    def receiveMailCopyFromDistributionLog( self, REQUEST ):
        """
            Receive copy email-message from distribution log
        """
        membership = getToolByName( self, 'portal_membership', None )
        if membership is None:
            return

        log_id = int(REQUEST.get('mail_to_receive'))
        msg = self.distribution_log[ log_id ]['message']

        try:
            subject = self.distribution_log[ log_id ]['subject']
        except:
            msg_catalog = getToolByName( self, 'msg', None )
            subject = msg_catalog('DOCFLOW LETTER')

        mailhost = aq_get( self, 'MailHost', None, 1 )
        user_email = membership.getAuthenticatedMember().getProperty('email')
        mailhost.send( msg, mto=[ user_email ], subject=subject, from_member=1, object_url=self.physical_path() )

        return REQUEST.RESPONSE.redirect( self.absolute_url( action='distribution_log_form', message="The email is sent.", \
            frame='inFrame' ) \
            )

    def manage_FTPget( self, REQUEST=None, RESPONSE=None ):
        """
            Get the document body for FTP download (also used for the WebDAV SRC)
        """
        hdrlist = self.getMetadataHeaders()

        if self.text_format == 'html':
            lang = self.Language()
            charset = getLanguageInfo( lang )['http_charset']
            hdrtext = '<meta http-equiv="Content-Type" content="text/html; charset=%s" />' % charset

            for name, content in hdrlist:
                if name.lower() == 'title':
                    continue
                hdrtext += '\n<meta name="%s" content="%s" />' % ( name, escape( str(content) ) )

            bodytext = _formattedBodyTemplate % {
                        'title'     : escape( self.Title() ),
                        'head'      : hdrtext,
                        'style'     : '',
                        'language'  : lang,
                        'font'      : self.getFontFamily(),
                        'resolution': self.getDocumentResolution(),
                        'body'      : self.EditableBody(),
                    }
        else:
            hdrtext  = formatRFC822Headers( hdrlist )
            bodytext = '%s\r\n\r\n%s' % ( hdrtext, self.text )

        return bodytext
    #
    # ===============================================================================================================
    #
    security.declareProtected( CMFCorePermissions.View, 'getChangesFrom' )
    def getChangesFrom( self, other, text = None ):
        """
            Returns HTML diff between *other* and this version.

            Arguments:

                'other' -- version object to compare against
                'text'  -- text to compare against

            Result:

                String containing HTML code.
        """
        current = self.getCurrentVersionId()

        # XXX should we check permissions on *other*?
        self.makeCurrent()
        b = self.CookedBody()

        if text != None:
            return HTMLDiff( b, text )

        other.makeCurrent()
        a = other.CookedBody()

        # restore selected version
        self.getVersion( current ).makeCurrent()

        return HTMLDiff( a, b )

    #security.declareProtected( CMFCorePermissions.View, 'hasExpiredTasks' )
    def hasExpiredTasks( self, show=None, returns='url' ):
        """
            Checks whether the document has expired tasks.

            Result:

                URL for task object or None.
        """
        if not hasattr(self, 'followup'):
            return None
        tasks = self.followup.getBoundTasks()
        if not tasks:
            return None

        expired_tasks = []

        for task in tasks:
            if ( task.isViewer() or show ) and not task.isFinalized() and task.expires() < DateTime():
                task_url = task.absolute_url(canonical=1, no_version=1) + '/view'
                if returns == 'tasks':
                    expired_tasks.append( task )
                elif returns == 'url':
                    return task_url
                else:
                    return task

        if returns == 'tasks': return expired_tasks
        return None

    security.declareProtected( CMFCorePermissions.View, 'hasTaskWithSignature' )
    def hasTaskWithSignature( self, template_id=None ):
        """
            Checks whether the document has a signature.

            Result:

                Returns user id list who made response for signature_task.
        """
        if not hasattr(self, 'followup'):
            return None
        if not template_id:
            return None

        x = template_id.split('|')
        if len(x) == 2:
            template = x[0]
            signature_date_position = x[1]
        else:
            template = x[0]
            signature_date_position = None

        template_ids = template.split(':')
        version_id = self.implements('isVersion') and self.getId() or self.getVersion().getId() 

        tasks = self.followup.getBoundTasks()
        if not tasks:
            return None

        bound_tasks = tasks
        for task in tasks:
            bound_tasks.extend( task.followup.getBoundTasks() )

        members = []
        for task in bound_tasks:
            if version_id and getattr( task, 'version_id', None ) != version_id:
                continue
            if task.task_template_id in template_ids:
                IsRequest = task.BrainsType() in ['request']
                IsSignatureRequest = task.BrainsType() in ['signature_request']
                responses = task.searchResponses()
                if not responses:
                    continue

                task_is_finalized = task.isFinalized() and task.ResultCode() == TaskResultCodes.TASK_RESULT_SUCCESS and 1 or 0

                if task_is_finalized and task.hasDelegationOfAuthority():
                    r_date = DateTime()
                    for r in responses:
                        if r['status'] in ['commit','sign','satisfy','informed']:
                            r_date = r['date']
                            break
                    for member in task.InvolvedUsers( no_recursive=1 ):
                        members.append( (member, r_date, signature_date_position) )

                elif IsSignatureRequest and ( task_is_finalized or len(task.InvolvedUsers( no_recursive=1 )) > 1 ):
                    for r in responses:
                        if r['status'] in ['sign'] and r['isclosed']:
                            members.append( (r['member'], r['date'], signature_date_position) )

                elif IsRequest:
                    for r in responses:
                        if r['status'] in ['satisfy']:
                            members.append( (r['member'], r['date'], signature_date_position) )

        return members

    #security.declareProtected( CMFCorePermissions.View, 'getInfoForLink' )
    def getInfoForLink( self, mode=1 ):
        """
            Returns the document title and registration info by category default registry.

            Result:

                String.
        """
        reg_info = ''

        category = self.getCategory()
        if not category or not hasattr(self, 'registry_data'):
            return None

        registry = None
        registry_uid = None
        RID = ''
        RegDate = ''
        entry = None

        for reg_id, reg_uids in self.registry_data.items():
            reg_uid = reg_uids[0]
            registry = getObjectByUid( self, reg_uid )
            RID = reg_id
            break

        if not RID:
            if mode > 0: return ''
            return None
        if mode == 'RID': return RID

        if registry is not None and 'creation_date' in registry.listColumnIds():
            entry = registry.getEntry( id=RID )
            if entry is not None:
                value = entry.get('creation_date')
                RegDate = '%s.%s.%d' % ( value.dd(), value.mm(), value.year() )

        if mode == -1: return entry

        msg = getToolByName( self, 'msg', None )

        if RegDate:
            if not mode or mode == 1:
                reg_info = ' ('+msg('RegN')+' %s, %s)' % ( RID, RegDate )
                x = self.title + reg_info
            elif mode == 2:
                reg_info = '%s %s %s %s' % ( msg('RegN'), RID, msg('of'), RegDate )
                x = reg_info
            elif mode == 3:
                reg_info = '%s %s' % ( msg('RegN'), RID )
                x = reg_info
            elif mode == 4:
                number = entry.getLinkedNumber()
                reg_info = '%s %s %s' % ( number[0], msg('of'), number[1] )
                x = reg_info
        elif mode:
            archive = getClientStorageType( self )
            if archive:
                if mode == 1:
                    reg_info = ' ('+msg('RegN')+' %s)' % RID
                elif mode == 4:
                    reg_info = '%s' % RID
                else:
                    reg_info = msg('RegN')+' %s' % RID
                x = reg_info
            else:
                x = msg('RegN')+' %s' % RID
        else:
            x = self.title

        return x


class Cooker( Implicit ):

    def __init__( self, view ):
        """
            Initialize class instance
        """
        self.cookForView = view

    def RenderAttribute( self, attr, value, style, param=None ):
        """
            The main method. Calls corresponding cooker method
            depending on attr.Type().
        """
        method_name = 'Cook%s' % attr.Type().capitalize()
        if hasattr( self, method_name ):
            name = attr.getId()
            return apply( getattr(self, method_name), ( attr, name, value, style, param ) )

        return str( value or '' )

    def CheckLinkedMethod( self, attr, name, value ):
        linked_method = attr.getLinkedMethod()

        if linked_method and linked_method[0] == 'CookedBodyTag':
            rendered = CookedBodyTag( attr, name, value )
            if self.cookForView:
                return rendered
            return '<span name="%s">%s</span>' % ( name, rendered )

        return None

    def CookBoolean( self, attr, name, value, style, param ):
        if not ( self.cookForView or attr.isReadOnly() or not attr.isEditable() ): #  or attr.isHidden()
            return '<input type="checkbox" name="%s" %s>' % ( name, value and 'checked="1"' or '' )

        x = self.CheckLinkedMethod( attr, name, value )
        if x is not None:
            return x

        rendered = getToolByName( self, 'msg' )( value and 'Yes' or 'No' )

        if self.cookForView:
            return rendered

        return '<span name="%s">%s</span>' % ( name, rendered )

    def CookText( self, attr, name, value, style, param ):
        if value is None:
            value = ''
        if not ( self.cookForView or attr.isReadOnly() or not attr.isEditable() ):  # or attr.isHidden()
            #return '<textarea name="%s">%s</textarea>' % ( name, escape( value, 1 ) )
            return '<textarea name="%s" %s>%s</textarea>' % ( name, style, escape(value, 1) )

        rendered = escape( value, 1 ).replace('\r', '').replace('\n', '<br>\n')

        if self.cookForView:
            return rendered

        return '<span name="%s">%s</span>' % ( name, rendered )

    def CookUserlist( self, attr, name, value, style, param ):
        if type(value) not in ( TupleType, ListType ):
            value = [ value ]

        membership = getToolByName( self, 'portal_membership', None )
        members_ids = membership.listMemberIds()

        if not ( self.cookForView or attr.isReadOnly() or not attr.isEditable() ): #  or attr.isHidden()
            #result = [ '<select %s name="%s" %s>' % (isMultiple and 'multiple' or '', name, style) ]
            result = [ '<select %s name="%s" %s>' % ( 'multiple', name, style ) ]

            for record in membership.listSortedUserNames(members_ids):
                result.append('<option value="%s" %s>%s</option>' \
                    % ( escape(record['user_id']), record['user_id'] in value and 'selected="1"' or '', \
                    escape( record['user_name'] ) ) )

            result.append('</select>')
            return '\n'.join(result)

        users = [ str(user and membership.getMemberBriefName(user) or '') for user in value]
        users = filter( None, users )
        rendered = escape( ', '.join( users ), 1 )

        if self.cookForView:
            return rendered

        return '<span name="%s">%s</span>' % ( name, rendered )

    def CookDate( self, attr, name, value, style, param ):
        #ignore style
        rendered = ""
        msg = getToolByName( self, 'msg' )

        if isinstance(value, StringType):
            rendered = value
        elif value:
            rendered = '%s %s %d' % ( value.dd(), msg( value.Mon() ), value.year() )

        if self.cookForView:
            return rendered

        if isinstance(value, StringType) or attr.isReadOnly() or not attr.isEditable():  # or attr.isHidden()
            return '<span name="%s">%s</span>' % ( name, rendered )

        #edit and not read-only
        select_to_show = []
        select_to_show.append(
            { 'select_name': "%s_day" % name,
              'item_value': value and value.day() or None,
              'range': range(1, 32),
              'func_show': None,
            }
        )

        def show_month( num, msg=msg ):
            return msg(Months[num-1])

        select_to_show.append(
            { 'select_name': "%s_month" % name,
              'item_value': value and value.month() or None,
              'range': range(1, 13),
              'func_show': show_month,
            }
        )

        y = value and value.year() or DateTime().year()
        select_to_show.append(
            { 'select_name': "%s_year" % name,
              'item_value': value and value.year() or None,
              'range': range(y-2, y+5),
              'func_show': None,
            }
        )

        result = [] #['<span>']
        for select_show in select_to_show:
            #IsDay = select_show['select_name'].find('_day') > 0
            #if IsDay:
            #    result.append( '«' )
            result.append( '<select name="%s">' % select_show['select_name'] )
            result.append( '<option value=>---</option>' )
            for item_value in select_show['range']:
                if select_show['func_show']:
                    item_show = apply( select_show['func_show'], (item_value,) )
                else:
                    item_show = str(item_value)
                result.append( '<option value="%s" %s>%s</option>' \
                    % ( str(item_value), item_value == select_show['item_value'] and 'selected="1"' or '', item_show ) )
            result.append( '</select>' )
            #if IsDay:
            #    result.append( '»' )
        
        #result.append ( '</span>' )
        return '\n'.join( result )

    def CookLines( self, attr, name, value, style, param ):
        selected = rendered = value
        isMultiple = type(value) in ( TupleType, ListType ) and attr.getOptions('multiple')

        #portal_info( 'HTMLDocument.CookLines', 'value: %s' % ( value, ) )

        if not isMultiple:
            rendered = [ str( value ) or '' ]
            selected = [ value ]

        rendered = escape( ', '.join( map( str, rendered ) ), 1 )

        #The problem is that getDefaultValue() returns list of all strings
        #instead of list of strings that are selected by default in 3.21
        if value == attr.getDefaultValue( default_only=1 ):
            rendered = ''
            selected = []

        if self.cookForView:
            return rendered

        if attr.isReadOnly() or not attr.isEditable(): #  or attr.isHidden()
            return '<span name="%s">%s</span>' % ( name, rendered )

        #edit and not read-only
        result = []
        result.append('<select name="%s" %s %s>' % ( name, isMultiple and 'multiple' or 'size="1"', style ))
        #result.append('<select name="%s">' % name)

        for line in attr.getDefaultValue():
            result.append( '<option value="%s" %s>%s</option>' \
                % ( escape(line,1), line in selected and 'selected' or '', escape(line) ) )
        else:
            result.append( '<option value=""></option>' )
        result.append( '</select>' )

        return '\n'.join( result )

    def CookItems( self, attr, name, value, style, param ):
        selected = rendered = value
        defvalue = attr.getDefaultValue( default_only=1 )

        #portal_info( 'HTMLDocument.CookItems', 'value: %s, defvalue: %s' % ( value, defvalue ) )
        nonselected = 'nonselected'

        def isDefValue( value, defvalue ):
            try:
                return value[0] == defvalue and 1 or 0
            except:
                return 0

        if isDefValue( value, nonselected ):
            rendered = [ '' ] #defvalue[0]['title']
        elif value:
            items = attr.getDefaultValue( id=value )
            rendered = [ x['title'] for x in items ]
        else:
            rendered = ''

        rendered = escape( ', '.join( map( str, rendered ) ), 1 )

        if self.cookForView:
            return rendered

        if attr.isReadOnly() or not attr.isEditable(): #  or attr.isHidden()
            return '<span name="%s">%s</span>' % ( name, rendered )

        #edit and not read-only
        result = []
        result.append('<select name="%s" %s>' % ( name, style ))

        for line in defvalue:
            result.append( '<option value="%s" %s>%s</option>' \
                % ( line['id'], line['id'] in selected and 'selected' or '', escape(line['title']) ) )
        else:
            result.append( '<option value=""></option>' )

        result.append( '</select>' )

        return '\n'.join( result )

    def CookLink( self, attr, name, value, style, param ):
        rendered = ''
        nonselected = 'nonselected'
        msg = getToolByName( self, 'msg', None )

        get_default = attr.getComputedDefault()

        if not value:
            if get_default:
                v = msg is not None and msg(nonselected) or rendered
            else:
                v = rendered
            return '<span name="%s%s">%s</span>' % ( name, param and '.'+param or '', v )
        elif get_default:
            values = attr.getDefaultValue( id=value )
        else:
            values = [ value ]

        style = style and ' %s' % style or ''
        len_values = len(values)

        for n in range(len_values):
            try:
                uid = values[n].get('uid')
                ob = uid and getObjectByUid( self, uid ) or None
            except:
                ob = None

            if ob is not None:
                if param:
                    if param.lower() == 'title':
                        v = ob.Title()
                    elif param.lower() == 'description':
                        v = ob.Description()
                    else:
                        v = ob.getCategoryAttribute( param )
                else:
                    v = ob.Title()
                if not v:
                    v = '&nbsp;'

                if self.cookForView:
                    rendered += '<a href="%s" target="_blank"%s>%s</a>' % ( ob.absolute_url( action='view' ) + '?expand=1', style, v )
                else:
                    rendered += '<span name="%s%s">%s</span>' % ( name, param and '.'+param or '', v )
            else:
                rendered += '<span name="%s%s">%s</span>' % ( name, param and '.'+param or '', \
                    msg is not None and msg(nonselected) or '%nbsp;' )

            if n+1 < len_values:
                rendered += '<br>'

        return rendered

    def CookInt( self, attr, name, value, style, param ):
        rendered = escape( str(value or ''), 1 )
        size = 3

        if not ( self.cookForView or attr.isReadOnly() or not attr.isEditable() ): #  or attr.isHidden()
            return '<input style="text-align:center;" type="text" name="%s" value="%s" size="%s" %s>' % ( name, rendered, size, style )

        if self.cookForView:
            return rendered

        return '<span name="%s">%s</span>' % ( name, rendered )

    def CookFloat( self, attr, name, value, style, param ):
        rendered = escape( str(value or ''), 1 )
        size = 10

        if not ( self.cookForView or attr.isReadOnly() or not attr.isEditable() ): #  or attr.isHidden()
            return '<input style="text-align:center;" type="text" name="%s" value="%s" size="%s" %s>' % ( name, rendered, size, style )

        if self.cookForView:
            return rendered

        return '<span name="%s">%s</span>' % ( name, rendered )

    def CookString( self, attr, name, value, style, param ):
        rendered = escape( str(value or ''), 1 )

        if not ( self.cookForView or attr.isReadOnly() or not attr.isEditable() ): #  or attr.isHidden()
            return '<input type="text" name="%s" value="%s" %s>' % ( name, rendered, style )

        if self.cookForView:
            return rendered

        return '<span name="%s">%s</span>' % ( name, rendered )

    def CookTable( self, attr, name, value, style, param ):
        rendered = ''
        nonselected = 'nonselected'
        msg = getToolByName( self, 'msg', None )

        cooked_table = CustomCookedTable( name )

        if not cooked_table or attr.isHidden():
            return '<span name="%s"></span>' % name

        # Column definitions
        columns = cooked_table['columns']
        enumerated = cooked_table.get('enumerated')

        membership = getToolByName( self, 'portal_membership', None )

        # Headers of table
        rendered += '%s' % ( cooked_table['tag_table'] or '<TABLE border="0">' )
        headers = ''
        if enumerated:
            headers += '<TH style="text-align:center">%s</TH>' % msg('#')
        headers += ''.join( [ '<TH>%s</TH>' % x['title'] for x in columns ] )
        rendered += '<TR>%s</TR>' % headers
        tag_number = cooked_table.get('tag_number') or '<TD style="vertical-align:middle" valign="middle" align="right">&nbsp;%s.&nbsp;</TD>'

        count = 0
        values = []

        if value and type(value) == type({}):
            count = value.get('count') or 0
            values = value.get('values') or []

        # Data rows
        for n in range(count):
            rendered += '<TR>'

            if enumerated:
                rendered += tag_number % str(n+1)

            for c in columns:
                column_id = c['id']
                column_type = c.get('type').lower()
                #column_style = c.get('style') and ' style="%"' % c['style']
                column_class = c.get('class') and ' class=%s' % c['class'] or ''

                v = values and len(values) > n and values[n].get(column_id) or ''

                if not ( self.cookForView or attr.isReadOnly() or not attr.isEditable() ):
                    if not column_type or column_type == 'string':
                        column_name = '%s:string' % column_id
                        v = escape( str(v), 1 )
                        size = c.get('size') and ' size="%s"' % c['size'] or ''
                        column_value = '<input%s type="text" name="%s" value="%s"%s>' % ( column_class, column_name, v, size )

                    elif column_type == 'text':
                        column_name = '%s' % column_id
                        v = escape( str(v), 1 )
                        rows = c.get('rows') and ' rows="%s"' % c['rows'] or ''
                        column_value = '<textarea%s name="%s"%s>%s</textarea>' % ( column_class, column_name, rows, v )

                    elif column_type == 'select':
                        column_name = '%s:list' % column_id
                        size = c.get('size') and ' size="%s"' % c['size'] or ''
                        multiple = c.get('multiple') and c['multiple'] and ' multiple' or ''

                        items = [ '<select%s%s%s name="%s">' % ( column_class, size, multiple, column_name ) ]

                        for record in c['value']:
                            items.append('<option value="%s" %s>%s</option>' \
                                % ( escape( record[0] ), v and record[0] in v and 'selected' or '', \
                                    escape( record[1] ) ) )

                        items.append('</select>')
                        column_value = '\n'.join(items)

                    elif column_type in [ 'user_group', 'user_list' ]:
                        column_name = '%s:list' % column_id
                        size = c.get('size') and ' size="%s"' % c['size'] or ''
                        multiple = c.get('multiple') and c['multiple'] and ' multiple' or ''

                        if column_type == 'user_group' and c['value']:
                            members_ids = membership.getGroupMembers( c['value'] )
                        else:
                            members_ids = membership.listMemberIds()

                        users = [ '<select%s%s%s name="%s">' % ( column_class, size, multiple, column_name ) ]
                        users.append('<option value="%s" %s>%s</option>' % ( \
                            nonselected, not v and 'selected' or '', msg(nonselected) or '' ))

                        for record in membership.listSortedUserNames(members_ids):
                            users.append('<option value="%s" %s>%s</option>' \
                                % ( escape( record['user_id'] ), v and record['user_id'] in v and 'selected' or '', \
                                    escape( record['user_name'] ) ) )

                        users.append('</select>')
                        column_value = '\n'.join(users)
                elif v:
                    if column_type == 'select':
                        for i in range(len(c['value'])):
                            if v == c['value'][i][0]:
                                break
                        column_value = c['value'][i][1] or '&nbsp;'
                    elif column_type in [ 'user_group', 'user_list' ]:
                        column_value = v != nonselected and membership.getMemberName( v ) or '&nbsp;'
                    else:
                        column_value = v

                else:
                    column_value = '&nbsp;'

                rendered += '%s%s</TD>' % ( c['tag_td'] or '<TD>', column_value )

            rendered += '</TR>'

        rendered += '</TABLE>'

        return '<span name="%s">%s</span>' % ( name, rendered )

    CookCurrency = CookFloat


InitializeVersionableClass( HTMLDocument )
InitializeClass( HTMLDocument )
