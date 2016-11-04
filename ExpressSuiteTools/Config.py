"""
Global settings for the product
$Id: Config.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 08/06/2009 ***

"""
__version__ = "$Revision: 1.0 $"[11:-2]

ProductName             = 'ExpressSuiteTools'

MultiSQLDBConnection    = 1
SQLDBConnectorID        = 'SQLDB'
connection_string       = '+%(instance)s %(user)s %(passwd)s /tmp/mysql.sock'
SQLDBUser               = 'x'

IsSQLCatalog            = 1

DisableMigration        = 1
MigrationRecursionLimit = 3000
MigrationSubtransactionThreshold = 1000

AutoUpdateObjects       = 1
AutoUpgradeObjects      = 0
AutoUpdateRemote        = 0

DisablePersistentActionsLog = 0
BindClassAttributes     = 0

MaxErrorLogEntries      = 100
MaxTracebackDepth       = 50
MaxObjectReprLength     = 200

DefaultAttachmentType   = 'application/octet-stream'
ErrorReportAddress      = 'KharlamovIE@tmk-group.com'

MailerName              = 'ExpressSuiteMail v%s'
MailInboxName           = 'INBOX'
MailDefaultInterval     = 15 # in seconds

DefaultSession          = 'session'
UseLDAPUserFolder       = 0

IsPortalDebug           = 1

PersonalFolders         = {
                            'favorites' : 'Favorites',
                            'searches'  : 'Search profiles',
                          }

GroupAccessPolicy       = 'all'

SaveImageFrames         = 0 #should ImageAttachment store rendered frames (in case of multi-framed tiff)
SaveImageDisplays       = 1 #should ImageAttachment store rendered displays

AttachmentTypes         = ( 'Image Attachment', 'File Attachment', )
UnindexableContents     = ( 'Guarded Entry', 'Discussion Item', )

WorkflowChains          = {
                            'heading_workflow' : [ 'Heading', 'Incoming Mail Folder', 'Outgoing Mail Folder', 'Fax Incoming Folder', ],
                            '__empty__': [ 'Task Item', 'Discussion Item', 'Search Profile', 'Registry', 'Business Procedure', ],
                          }

NoEmailedExtensions     = ['.mht', '.mhtml'] # FIX IT 
ImageExtensions         = ['.gif', '.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff']
FaxableExtensions       = ['.txt', '.html', '.doc', '.xls', '.tif', '.gif', '.jpg', '.bmp', '.png', '.pdf']
FacsimileExtensions     = ['.gif', '.jpg']

allowed_column_types    = ( 'string', 'text', 'float', 'int' , 'boolean', 'date', 'listitem', 'items' )
DocumentLinkProperties  = [ 'Title', 'Creator' ]

FileExtensionMap        = {
                            'txt' : 'text/plain',
                            'js'  : 'text/javascript',
                            'css' : 'text/css',
                            'ico' : 'image/x-icon',
                            'doc' : 'application/msword',
                          }

SitePresentationLevels  = (
                            { 'title' : 'Ordinary object', 'max_count' : 0 },
                            { 'title' : 'Primary news', 'max_count' : 1 },
                            { 'title' : 'Secondary news', 'max_count' : 3 },
                          )

PublicViews             = [ 'public', 'gui' ]
SkinViews               = [ 
                            'app', 'calendar', 'categories', 'comments', 'common', 'discussions',
                            'fs_objects', 'gui', 'heading', 'htmldocument', 'htmlcard', 'mail_templates', 'membership',
                            'portal', 'public', 'registry', 'report', 'tasks', 'scheduler', 
                          ]

DefaultLanguage         = 'ru'
HasTLSLocaleBug         = 0

Languages               = { 'en' : {
                                'title'          : 'English',
                                'posix_locale'   : 'en_US.ISO8859-1',
                                'win32_locale'   : 'English_United States.1252',
                                'http_charset'   : 'windows-1251', #'iso-8859-1',
                                'mail_charset'   : 'windows-1251', #'iso-8859-1',
                                'system_charset' : 'koi8-r', #'iso8859-1',
                                'python_charset' : 'cp1251',
                                'general_font'   : 'Verdana, Arial, Helvetica, sans-serif',
                                'message_font'   : 'Arial, Verdana, Helvetica, sans-serif',
                                'input_font'     : 'Verdana, Arial, Helvetica, sans-serif',
                                'symbol_font'    : 'Times New Roman, Times, serif',
                                'title_font'     : 'Arial, Verdana, Helvetica, sans-serif',
                                'document_font'  : 'Verdana, Arial, Helvetica, sans-serif',
                            },

                            'ru' : {
                                'title'          : 'Russian',
                                'posix_locale'   : 'ru_RU.CP1251',
                                'win32_locale'   : 'Russian_Russia.1251',
                                'http_charset'   : 'windows-1251',
                                'mail_charset'   : 'windows-1251',
                                'system_charset' : 'koi8-r',
                                'python_charset' : 'cp1251',
                                'general_font'   : 'Verdana, Helvetica, Tahoma, Arial, sans-serif',
                                'message_font'   : 'Arial, Verdana, Helvetica, sans-serif',
                                'input_font'     : 'Verdana, Helvetica, Tahoma, Arial, sans-serif',
                                'symbol_font'    : 'Times New Roman, Times, serif',
                                'title_font'     : 'Arial, Verdana, Helvetica, sans-serif',
                                'document_font'  : 'Verdana, Helvetica, Tahoma, Arial, sans-serif',
                            },

                            'kk' : {
                                'title'          : 'Kazakh',
                                'posix_locale'   : 'ru_RU.CP1251',
                                'win32_locale'   : 'Kazakh_Kazakstan.1251',
                                'http_charset'   : 'windows-1251',
                                'mail_charset'   : 'windows-1251',
                                'system_charset' : 'cp1251',
                                'python_charset' : 'cp1251',
                                'general_font'   : 'KZ Arial',
                                'message_font'   : 'KZ Arial',
                                'input_font'     : 'KZ Arial',
                                'symbol_font'    : 'Times New Roman, Times, serif',
                                'title_font'     : 'KZ Arial',
                                'document_font'  : 'KZ Arial',
                            },
                          }

CharsetEntityMap        = {
                            'windows-1251' : {
                                '\x91' : '&lsquo;',
                                '\x92' : '&rsquo;',
                                '\x93' : '&ldquo;',
                                '\x94' : '&rdquo;',
                                '\xAB' : '&laquo;',
                                '\xBB' : '&raquo;',
                                '\x85' : '&hellip;',
                                '\x88' : '&euro;',
                                '\x95' : '&bull;',
                                '\x96' : '&ndash;',
                                '\x97' : '&mdash;',
                                '\x99' : '&trade;',
                                '\xA9' : '&copy;',
                                '\xAE' : '&reg;',
                                '\xA7' : '&sect;',
                                '\xB0' : '&deg;',
                                '\xB1' : '&plusmn;',
                                '\xB9' : '&#8470;',
                            },
                          }

LanguageEntitiesMap     = {
                            'kk' : {
                                '&#1240;' : '\xAA',
                                '&#1186;' : '\x8C',
                                '&#1170;' : '\x81',
                                '&#1198;' : '\x87',
                                '&#1200;' : '\xA6',
                                '&#1178;' : '\x8D',
                                '&#1256;' : '\xA4',
                                '&#1210;' : '\x8E',
                                '&#1241;' : '\xBA',
                                '&#1187;' : '\x9C',
                                '&#1171;' : '\x83',
                                '&#1199;' : '\x89',
                                '&#1201;' : '\xB1',
                                '&#1179;' : '\x9D',
                                '&#1257;' : '\xB5',
                                '&#1211;' : '\x9E',
                            },
                          }

TransliterationMap      = {
                            'ru' : {
                                # transliteration from CP1251 (Russian) text [GOST 16876-71]
                                # differences from GOST - hard (") and soft (') signs are replaced to empty strings
                                '\xc0':'A',  '\xc1':'B',   '\xc2':'V', '\xc3':'G', '\xc4':'D', '\xc5':'E',  '\xc6':'Zh', '\xc7':'Z',
                                '\xc8':'I',  '\xc9':'Jj',  '\xca':'K', '\xcb':'L', '\xcc':'M', '\xcd':'N',  '\xce':'O',  '\xcf':'P',
                                '\xd0':'R',  '\xd1':'S',   '\xd2':'T', '\xd3':'U', '\xd4':'F', '\xd5':'Kh', '\xd6':'C',  '\xd7':'Ch',
                                '\xd8':'Sh', '\xd9':'Shh', '\xda':'' , '\xdb':'Y', '\xdc':'',  '\xdd':'Eh', '\xde':'Ju', '\xdf':'Ja',
                                '\xe0':'a',  '\xe1':'b',   '\xe2':'v', '\xe3':'g', '\xe4':'d', '\xe5':'e',  '\xe6':'zh', '\xe7':'z',
                                '\xe8':'i',  '\xe9':'ji',  '\xea':'k', '\xeb':'l', '\xec':'m', '\xed':'n',  '\xee':'o',  '\xef':'p',
                                '\xf0':'r',  '\xf1':'s',   '\xf2':'t', '\xf3':'u', '\xf4':'f', '\xf5':'kh', '\xf6':'c',  '\xf7':'ch',
                                '\xf8':'sh', '\xf9':'shh', '\xfa':'',  '\xfb':'y', '\xfc':'',  '\xfd':'eh', '\xfe':'ju', '\xff':'ja',
                                '\xa8':'Jo', '\xb8':'jo',
                            },

                            'kk' : ( 'ru', {} ),
                        }

FollowupMenu            = 'followup_menu'
UserMenu                = 'user'
GlobalMenu              = 'global'
SearchMenu              = 'search'
NavTreeMenu             = 'navTree'
NavMembersMenu          = 'navMembers'
HelpMenu                = 'help'

Months                  = [ 'Jan','Feb','Mar','Apr','may','Jun','Jul','Aug','Sep','Oct','Nov','Dec' ]

Icon2FileMap            = {
                            'gif'  : 'image_icon.gif',
                            'jpg'  : 'image_icon.gif',
                            'txt'  : 'doc_icon.gif',
                            'doc'  : 'word_icon.gif',
                            'htm'  : 'doc_icon.gif',
                            'html' : 'doc_icon.gif',
                          }

# ================================================================================================================

from AccessControl import Permissions as ZopePermissions
from Products.CMFCore import permissions as CMFCorePermissions

try: from Products.ExternalEditor import ExternalEditorPermission as UseExternalEditorPerm
except ImportError: UseExternalEditorPerm = 'Use external editor'

AnonymousRole                   = 'Anonymous'
MemberRole                      = 'Member'
ManagerRole                     = 'Manager'
VisitorRole                     = 'Visitor'

OwnerRole                       = 'Owner'
EditorRole                      = 'Editor'
ReaderRole                      = 'Reader'
WriterRole                      = 'Writer'
AuthorRole                      = 'Author'
VersionOwnerRole                = 'VersionOwner'

WorkflowChiefRole               = 'WorkflowChief'

ManagedLocalRoles               = ( EditorRole, WriterRole, ReaderRole, AuthorRole, WorkflowChiefRole )
ManagedRoles                    = ( MemberRole, ManagerRole, OwnerRole, EditorRole, ReaderRole, WriterRole, AuthorRole, VersionOwnerRole, WorkflowChiefRole )

EmployPortalContentPerm         = 'Employ portal content'
PublishPortalContentPerm        = 'Publish portal content'
ArchivePortalContentPerm        = 'Archive portal content'

UpdateRemoteObjectsPerm         = 'Update remote objects'

AddMailServerObjectsPerm        = 'Add MailServer objects'
UseMailServerServicesPerm       = 'Use MailServer services'

AddMailHostObjectsPerm          = ZopePermissions.add_mailhost_objects
UseMailHostServicesPerm         = ZopePermissions.use_mailhost_services

WebDAVLockItemsPerm             = 'WebDAV Lock items'
WebDAVUnlockItemsPerm           = 'WebDAV Unlock items'

AddDTMLDocumentsPerm            = 'Add DTML Documents'

CreateObjectVersionsPerm        = 'Create object versions'
MakeVersionPrincipalPerm        = 'Make version principal'

CopyOrMovePerm                  = 'Copy or Move'
UseErrorLoggingPerm             = 'Log Site Errors'
ManageCommentsPerm              = 'Manage comments'

TASK_RESULT_SUCCESS             = 'success'
TASK_RESULT_FAILED              = 'failed'
TASK_RESULT_CANCELLED           = 'cancelled'

TASK_INSPECTED_SUCCESSFULL      = ( 'inspected', )

TASK_COMMITS_SUCCESSFULL        = ( 'satisfy','sign','commit','inspected', )
TASK_COMMITS_FAILURE            = ( 'revise','reject','failure', )

DEMAND_REVISION_SUCCESS         = 'success'
DEMAND_REVISION_FAILED          = 'revision failed'
DEMAND_REVISION_DEFAULT         = 'should be revised'
DEMAND_REVISION_CURRENT         = 'current revision'

# ================================================================================================================

class Roles: pass

class Permissions: pass

class TaskResultCodes: pass

class TaskCommits: pass

class DemandRevisionCodes: pass

for name, value in globals().items():
    if name[-4:] == 'Role':
        #Roles.__dict__[ name[:-4] ] = value
        setattr( Roles, name[:-4], value )
    elif name[-4:] == 'Perm':
        #Permissions.__dict__[ name[:-4] ] = value
        setattr( Permissions, name[:-4], value )
    elif name[:11] == 'TASK_RESULT':
        #TaskResultCodes.__dict__[ name ] = value
        setattr( TaskResultCodes, name, value )
    elif name[:14] == 'TASK_INSPECTED':
        #TaskCommits.__dict__[ name ] = value
        setattr( TaskCommits, name, value )
    elif name[:12] == 'TASK_COMMITS':
        #TaskCommits.__dict__[ name ] = value
        setattr( TaskCommits, name, value )
    elif name[:15] == 'DEMAND_REVISION':
        #DemandRevisionCodes.__dict__[ name ] = value
        setattr( DemandRevisionCodes, name, value )

class AppClasses: pass

class BasesRecursive: pass

# ================================================================================================================

ManagedPermissions = (
    CMFCorePermissions.AccessContentsInformation,
    CMFCorePermissions.ListFolderContents,
    CMFCorePermissions.ModifyPortalContent,
    CMFCorePermissions.View,
    CMFCorePermissions.ManageProperties,
    CMFCorePermissions.ReplyToItem,
    ZopePermissions.delete_objects,
    ZopePermissions.take_ownership,
    Permissions.WebDAVLockItems,
    Permissions.WebDAVUnlockItems,
    Permissions.CreateObjectVersions,
    Permissions.MakeVersionPrincipal,
)

PortalPermissions = (
    #( CMFCorePermissions.AccessContentsInformation, [], 1 ),
    #( CMFCorePermissions.AccessFuturePortalContent, [], 1 ),

    ( CMFCorePermissions.AccessInactivePortalContent,   [ MemberRole, ], 1 ),
    ( CMFCorePermissions.AddPortalContent,              [ ManagerRole, OwnerRole, EditorRole, WriterRole, AuthorRole ], 1 ),
    ( CMFCorePermissions.AddPortalFolders,              [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( CMFCorePermissions.ChangePermissions,             [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( CMFCorePermissions.FTPAccess,                     [ ManagerRole, OwnerRole ], 1 ),
    ( CMFCorePermissions.ListPortalMembers,             [ ManagerRole, MemberRole ], 1 ),
    ( CMFCorePermissions.ListUndoableChanges,           [ ManagerRole, MemberRole ], 1 ),
    ( CMFCorePermissions.ManagePortal,                  [ ManagerRole ], 1 ),
    ( CMFCorePermissions.ManageProperties,              [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( CMFCorePermissions.ModifyPortalContent,           [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( CMFCorePermissions.ReplyToItem,                   [ ManagerRole, OwnerRole, MemberRole ], 1 ),
    ( CMFCorePermissions.RequestReview,                 [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( CMFCorePermissions.SetOwnPassword,                [ ManagerRole, MemberRole ], 1 ),
    ( CMFCorePermissions.SetOwnProperties,              [ ManagerRole, MemberRole ], 1 ),
    ( CMFCorePermissions.UndoChanges,                   [ ManagerRole, MemberRole ], 1 ),
    ( CMFCorePermissions.View,                          [ ManagerRole, OwnerRole, EditorRole, MemberRole ], 0 ),
    ( CMFCorePermissions.ViewManagementScreens,         [ ManagerRole ], 1 ),

    ( ZopePermissions.change_configuration,             [ ManagerRole, OwnerRole ], 1 ),
    ( ZopePermissions.delete_objects,                   [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( ZopePermissions.take_ownership,                   [ ManagerRole, OwnerRole, EditorRole ], 1 ),

    ( Permissions.AddDTMLDocuments,                     [ ManagerRole ], 1 ),
    ( Permissions.AddMailHostObjects,                   [ ManagerRole ], 1 ),
    ( Permissions.AddMailServerObjects,                 [ ManagerRole ], 1 ),
    ( Permissions.ArchivePortalContent,                 [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( Permissions.CopyOrMove,                           [ ManagerRole, OwnerRole, MemberRole ], 1 ),
    ( Permissions.CreateObjectVersions,                 [ ManagerRole, OwnerRole, EditorRole, WriterRole ], 1 ),
    ( Permissions.EmployPortalContent,                  [ ManagerRole, EditorRole ], 1 ),
    ( Permissions.MakeVersionPrincipal,                 [ ManagerRole, OwnerRole ], 1 ),
    ( Permissions.ManageComments,                       [ ManagerRole ], 1 ),
    ( Permissions.PublishPortalContent,                 [ ManagerRole, EditorRole ], 1 ),
    ( Permissions.UpdateRemoteObjects,                  [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( Permissions.UseErrorLogging,                      [ ManagerRole ], 1 ),
    ( Permissions.UseExternalEditor,                    [ ManagerRole, MemberRole ], 1 ),
    ( Permissions.UseMailHostServices,                  [ ManagerRole, EditorRole ], 1 ),
    ( Permissions.UseMailServerServices,                [ ManagerRole, EditorRole ], 1 ),
    ( Permissions.WebDAVLockItems,                      [ ManagerRole, OwnerRole, EditorRole ], 1 ),
    ( Permissions.WebDAVUnlockItems,                    [ ManagerRole, OwnerRole, EditorRole ], 1 ),
)

# ================================================================================================================

default_member_activity_columns = [ \
    ( 'login_time',    'DATETIME',                                None                   ), 
    ( 'activity',      'INT UNSIGNED DEFAULT 0',                  None                   ), 
    ( 'user_runtime',  'INT UNSIGNED DEFAULT 0',                  None                   ), 
    ( 'time_average',  'FLOAT DEFAULT 0.0',                       None                   ),
]

default_seen_by_log_columns = [ \
    ( 'ID',            'CHAR(23) ASCII NOT NULL',                'INDEX USING BTREE(ID)' ), 
    ( 'seen_time',     'DATETIME',                                None                   ), 
    ( 'member',        'CHAR(30) ASCII NOT NULL',                 None                   ), 
]

default_response_collection_columns = [ \
    ( 'ID',            'CHAR(30) ASCII NOT NULL',                'INDEX USING BTREE(ID)' ), 
    ( 'date',          'DATETIME',                                None                   ),
    ( 'member',        'CHAR(30) ASCII NOT NULL',                'INDEX (member)'        ),
    ( 'status',        'CHAR(20) ASCII NOT NULL',                'INDEX (status)'        ),
    ( 'layer',         'CHAR(20) ASCII NOT NULL',                'INDEX (layer)'         ),
    ( 'text',          'TEXT(4000) NULL',                         None                   ),
    ( 'isclosed',      'TINYINT(1) DEFAULT 0',                   'INDEX (isclosed)'      ),
    ( 'attachment',    'VARCHAR(500) CHARACTER SET latin1 NULL',  None                   ),
    ( 'uip',           'CHAR(15) ASCII NULL',                     None                   ),
    ( 'remarks',       'VARCHAR(400) NULL',                       None                   ),
    ( 'response_id',   'INT NOT NULL DEFAULT 0',                  None                   ),
    ( 'task_id',       'CHAR(15) ASCII NOT NULL',                 None                   ),
]

default_registries = [ \
    ( 'ID',            'CHAR(100) ASCII NOT NULL',               'INDEX USING BTREE(ID)' ), 
    ( 'prefix',        'CHAR(2)',                                'INDEX (prefix)'        ), 
    ( 'counter',       'INT(8) DEFAULT 0',                       ''                      ), 
    ( 'daily_counter', 'INT(3) DEFAULT 0',                       ''                      ), 
]

CheckZODBBeforeInstall  = 1
DropZODBContent         = 0

# ================================================================================================================
