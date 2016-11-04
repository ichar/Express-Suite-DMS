"""
BackupFSRoot class
$Id: BackupFSRoot.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 20/12/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from zLOG import LOG, TRACE, INFO
from Globals import DTMLFile
from Globals import InitializeClass

from ZODB.FileStorage.FileStorage import FileStorageError

from AccessControl import ClassSecurityInfo
from Acquisition import aq_parent
from DateTime import DateTime
from OFS.ObjectManager import ObjectManager
from OFS.SimpleItem import SimpleItem

from Products.ExternalMethod import ExternalMethod
from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.utils import getToolByName

from SimpleObjects import Persistent
from CustomDefinitions import PortalInstance
from TemporalExpressions import DailyTE

import os

DEFAULT_CONTEXT = '/common'

pack_running = None
backup_running = None


class BackupFSRoot( Persistent, SimpleItem, ObjectManager ):
    """ 
        Backup FileStorage Root. 

        Provides a way to non-sites-conflict database backup and pack. 
        Saves whole the database file Data.fs. There is only one instance 
        (id="ExpressSuiteBackup") in the root folder in the database being created.
    """
    _class_version = 1.00

    manage_options = (
        {'label':'View',     'action':'view_properties'},
        {'label':'Security', 'action':'manage_access'},
    )

    security = ClassSecurityInfo()

    _view_properties = DTMLFile('dtml/manageSitesList', globals())
    
    security.declareProtected(CMFCorePermissions.ManagePortal, 'view_properties')
    def view_properties( self, REQUEST ):
        """
            Returns interface for view properties
        """
        return self._view_properties()

    def __init__( self, id='ExpressSuiteBackup', title="Backup File Storage Root object" ):
        """
            Creates new instance and sets to default all properties.

            Arguments:

                'id' -- identifier
                'title' -- object's title

        """
        self.id = id
        self.title = title

        self.pack_db_task_id = None
        self.backup_db_task_id = None

        self.app_with_sceduler_URL = None

        self._packOptions = {}
        self._packOptions['pack_days'] = 0
        self._packOptions['pack_hours'] = 0
        self._packOptions['pack_minutes'] = 0
        self._packOptions['pack_older'] = 0

        self._backupOptions = {}
        self._backupOptions['backup_days'] = 0
        self._backupOptions['backup_hours'] = 0
        self._backupOptions['backup_minutes'] = 0
        self._backupOptions['backup_copies'] = 1
        self._backupOptions['backup_path'] = ''
        self._backupOptions['arc_program'] = os.name=='posix' and 'tar' or ''

        self._p_changed = 1

    def _initstate( self, mode ):
        """ 
            Initializes attributes
        """
        if not Persistent._initstate(self, mode):
            return 0
            
        if getattr( self, '_appPathList', None ) is not None:
            del(self._appPathList)
            
        if getattr( self, 'archives', None ) is None:
            # in archives is stored information about archivers that may be used.
            self.archives = {
                'tar': ('tar -czf', 'tgz'), 
                'rar': ('rar a', 'rar'), 
                'WinRAR': ('WinRar a', 'rar'), 
                'WinZip': ('wzzip -a', 'zip')
            }

        if getattr(self, '_notified_members', None) is None:
            self._notified_members = []

        return 1
    
    security.declareProtected(CMFCorePermissions.ManagePortal, 'getPackDBoptions')
    def getPackDBoptions( self ):
        """ 
            Returns pack options.

            Used by PropertiesTool. 

            Result:

                Dictionary.
        """
        return self._packOptions

    security.declareProtected(CMFCorePermissions.ManagePortal, 'getBackupDBoptions')
    def getBackupDBoptions( self ):
        """ 
            Return backup options.

            Used by PropertiesTool.

            Result:

                Dictionary.
        """
        return self._backupOptions

    security.declareProtected(CMFCorePermissions.ManagePortal, 'listArchivers')
    def listArchivers( self ):
        """ 
            Returns pairs from self.archives (without file extensions).

            Those pairs are: archiver name and command. Used by PropertiesTool.

            Result:

                Tuple.
        """
        return [ ( key, self.archives[key][0] ) for key in self.archives.keys() ]

    #Creates external method 'BackupFileStorage' 
    #(file: ExpressSuiteCore.backup_zodb, method: backup_fs) and stores it in self.
    def manage_afterAdd( self, item=None, container=None ):
        i = ExternalMethod.ExternalMethod('BackupFileStorage', 'Backup FileStorage external method', \
                'ExpressSuiteTools.backup_zodb', 'backup_fs')
        self._setObject('BackupFileStorage', i)

    security.declareProtected(CMFCorePermissions.ManagePortal, 'backup')
    def backup( self, *args ):
        """ 
            Wrapper for external method backup_fs() from backup_zodb.py. 

            portal_scheduler can not use external methods, so this is a trick.
            Append to *args connection to DB to determine it's name and location.
            Nices priority by 10 and calls external method 'BackupFileStorage'. 
            Then restores priority.

            Arguments:

                'num_copies' -- Maximum number of copies to store.
                'backup_path' -- Path where to save backups ('' by default - this means 
                    to save all backups in the 'var' folder of Zope).
                'arc_program_data' -- tuple with archiver program and file extension 
                    (by default is ('', '')).
        """
        global backup_running
        if backup_running:
            return 'Backup of database is already started'
        LOG('BackupFSRoot.backup', INFO, "= STARTED.")

        backup_running = 1

        except_text=''
        #oldAppObject = self.unrestrictedTraverse( self.app_with_sceduler_URL, None )
        context = self.unrestrictedTraverse( DEFAULT_CONTEXT, None )
        ps = PortalInstance( context )
        instance = ps['instance']
        #lower our priority
        try: os.nice(10)
        except: pass

        try:
            num_copies = args[0]
            backup_path = args[1]
            arc_program_data = args[2]

            if instance:
                arc_program_data = ( arc_program_data[0], '%s.%s' % ( instance, arc_program_data[1] ) )

            args = ( num_copies, backup_path, arc_program_data )
            apply(self['BackupFileStorage'], args, {'connection':self._p_jar})
            info = ('%s/Data.fs.1.%s' % ( backup_path, arc_program_data[1]), \
                    arc_program_data[0], \
                    str(num_copies) \
                    )
            self.sendBackupNotify( info=info )
        except 'BError', except_text:
            raise
            backup_running = None
            self.sendBackupNotify( except_text=except_text, info=str(args) )
        except:
            backup_running = None
            raise

        try: os.nice(-10)
        except: pass

        backup_running = 0

        LOG('BackupFSRoot.backup', INFO, "= FINISHED.")
        return except_text and ('Backup error: '+except_text) or 'Backup copy has been created'

    security.declareProtected(CMFCorePermissions.ManagePortal, 'pack')
    def pack( self, days=0 ):
        """ 
            Packs database. Remove objects revisions older than days.

            Returns 'Database have not been packed' or 'Database have been packed'.

            Arguments:

                'days' -- Objects revisions older than days will be removed from DB.

            Result:

                String.
        """
        global pack_running
        if pack_running:
            return 'Pack of database is already started'
        LOG('BackupFSRoot.pack', INFO, "= STARTED(pack revisions older that %s days)." % days)

        pack_running = 1

        result = 'Database have not been packed'
        app = aq_parent(self)
        cpl = getattr(app, 'Control_Panel') #ApplicationManager
        #lower our priority
        try: os.nice(10)
        except: pass

        try:
            cpl.manage_pack(days)
            result = 'Database have been packed'
        except FileStorageError:
            # already packed
            pass

        # remove data.fs.old
        try: os.remove(self._p_jar.db().getName()+'.old')
        except OSError: pass
        try: os.nice(-10)
        except: pass

        pack_running = 0

        LOG('BackupFSRoot.pack', INFO, "= FINISHED.")
        return result

    def _areChanges( self, props, options ):
        """ 
            Updates options dictionary with data given in props.

            Returns true if any changes were made.

            Arguments:

                'props' -- dictionary containing properties

                'options' -- subdictionary (options.keys() are subset of props.keys())

            Result: 

                Boolean.
        """
        are_changes = 0
        for key in options.keys():
            if props.has_key(key) and props[key] is not None and props[key] != options[key]:
                are_changes = 1
                options[key] = props[key]
                self._p_changed = 1
        return are_changes

    security.declareProtected(CMFCorePermissions.ManagePortal, 'editProperties')
    def editProperties( self, appURL, props ):
        """
            Edits pack & backup props.

            The feature is that we use portal_scheduler of that site, 
            from which we change properties. If 'Backup now' button was 
            pushed, calls backup(). If 'Pack now' button was pushed, 
            calls pack(). Changes properties of scheduled tasks according props.

            Arguments:

               'appURL' -- URL to the App object, portal_scheduler of which to use.

               'props' -- dictionary with [new] properties.

            Returns:

               'Backup copy has been created' (if 'Backup now' button was pushed).

                Result of the pack() function (If 'Pack now' button was pushed).

                Error message (if error occurred).

                None if ok.

            Result:

                String or None if ok.
        """
        if props.has_key('notified_members'):
            self._notified_members = props['notified_members']
        else:
            self._notified_members = []

        if props.has_key('backup_now'):
            #pressed 'Backup now' button
            return self.backup( self._backupOptions['backup_copies'], \
                      self._backupOptions['backup_path'], \
                      self.archives.get(self._backupOptions['arc_program'], ('',''))[:] )

        elif props.has_key('pack_now'):
            #pressed 'Pack now' button
            return self.pack( self._packOptions['pack_older'] )

        else:
            #Pressed 'Change' button
            oldAppObject = None
            if self.app_with_sceduler_URL is not None:
                oldAppObject = self.unrestrictedTraverse( self.app_with_sceduler_URL, None )
            if oldAppObject is not None:
                oldScheduler = getattr( oldAppObject, 'portal_scheduler', None )
            else:
                oldScheduler = None

            newAppObject = self.unrestrictedTraverse( appURL, None )
            if newAppObject is not None:
                newScheduler = getattr( newAppObject, 'portal_scheduler', None )
            else:
                newScheduler = None

            new_task_pk = new_task_bk = appURL != self.app_with_sceduler_URL
            #determine do we need schedule new pack task or just change properties
            try:
                pack_task = oldScheduler.getScheduleElement( self.pack_db_task_id )
            except:
                pack_task = None
            if ( oldScheduler is not None and pack_task is None ) or oldScheduler is None:
                new_task_pk = 1
                self.pack_db_task_id = None

            #determine do we need schedule new backup task or just change properties
            try:
                backup_task = oldScheduler.getScheduleElement( self.backup_db_task_id )
            except:
                backup_task = None
            if ( oldScheduler is not None and backup_task is None ) or oldScheduler is None:
                new_task_bk = 1
                self.backup_db_task_id = None

            any_changes_bk = self._areChanges(props, self._backupOptions)
            if not self.archives.has_key( self._backupOptions['arc_program'] ):
                self._backupOptions['arc_program'] = ''
                self._p_changed = 1
                any_changes_bk = 1

            any_changes_pk = self._areChanges(props, self._packOptions)

            backup_days = self._backupOptions['backup_days']
            pack_days = self._packOptions['pack_days']
            now = DateTime()

            hours_bk = self._backupOptions['backup_hours']
            minutes_bk = self._backupOptions['backup_minutes']
            try:
                timeNext_bk = DateTime(now.year(), now.month(), now.day(), hours_bk, minutes_bk )
            except:
                return "Invalid backup time"

            hours_pk = self._packOptions['pack_hours']
            minutes_pk = self._packOptions['pack_minutes']
            try:
                timeNext_pk = DateTime(now.year(), now.month(), now.day(), hours_pk, minutes_pk )
            except:
                return "Invalid pack time"

            if new_task_bk or self.backup_db_task_id is None:
                #need to schedule new task
                if self.backup_db_task_id is not None:
                    if oldScheduler is not None:
                        oldScheduler.delScheduleElement( self.backup_db_task_id )
                        self.backup_db_task_id = None
                    else:
                        self.backup_db_task_id = None
                if backup_days and newScheduler is not None:
                    temporal_expr = DailyTE( hours_bk, minutes_bk, 0, backup_days )
                    self.backup_db_task_id = newScheduler.addScheduleElement( \
                        self.backup,
                        temporal_expr=temporal_expr,
                        title='Backup Database',
                        args=( self._backupOptions['backup_copies'],
                               self._backupOptions['backup_path'], 
                               self.archives.get( self._backupOptions['arc_program'], ('', '') )[:]
                        )
                    )
                self.app_with_sceduler_URL = appURL
            elif any_changes_bk:
                #just change properties of backup task
                if backup_days and newScheduler is not None:
                    se = newScheduler.getScheduleElement( self.backup_db_task_id )
                    temporal_expr = DailyTE( hours_bk, minutes_bk, 0, backup_days )
                    se.setTemporalExpression( temporal_expr )
                    se.method_args = ( self._backupOptions['backup_copies'],
                                       self._backupOptions['backup_path'],
                                       self.archives.get(self._backupOptions['arc_program'], ('', ''))[:]
                                     )
                else:
                    newScheduler.delScheduleElement(self.backup_db_task_id)
                    self.backup_db_task_id = None

            #pack properties
            if new_task_pk or self.pack_db_task_id is None:
                if self.pack_db_task_id is not None:
                    if oldScheduler is not None:
                        oldScheduler.delScheduleElement(self.pack_db_task_id)
                        self.pack_db_task_id = None
                    else:
                        self.pack_db_task_id = None
                if pack_days and newScheduler is not None:
                    temporal_expr = DailyTE( hours_pk, minutes_pk, 0, pack_days )
                    self.pack_db_task_id = newScheduler.addScheduleElement( \
                        self.pack,
                        temporal_expr=temporal_expr,
                        title='Pack Database', 
                        args=( self._packOptions['pack_older'], )
                    )
                self.app_with_sceduler_URL = appURL
            elif any_changes_pk:
                if pack_days and newScheduler is not None:
                    se = newScheduler.getScheduleElement( self.pack_db_task_id )
                    temporal_expr = DailyTE( hours_pk, minutes_pk, 0, pack_days )
                    se.setTemporalExpression( temporal_expr )
                    se.method_args = ( self._packOptions['pack_older'], )
                else:
                    newScheduler.delScheduleElement(self.pack_db_task_id)
                    self.pack_db_task_id = None

        return None

    def isPackTaskActive( self, app_url ):
        """
            Returns state of pack task.

            Returns 0 if task is dead, 1 if task is alive, but is assigned 
            to another App object, 2 if task is alive and is assigned to 
            App object with given URL.

            Arguments:

                'app_url' -- URL of the App object to check.

            Result:

                0, 1 or 2.
        """
        return self._isTaskAlive( app_url, pack_task=1 )

    def isBackupTaskActive( self, app_url ):
        """
            Returns state of backup task.

            Returns 0 if task is dead, 1 if task is alive, but is assigned 
            to another App object, 2 if task is alive and is assigned 
            to App object with given URL.

            Arguments:

                'app_url' -- URL of the App object to check.

            Result:

                0, 1 or 2.
        """
        return self._isTaskAlive( app_url, pack_task=0 )

    def _isTaskAlive( self, app_url, pack_task ):
        """ 
            Checks state of pack or backup task for the App object with app_url URL.

            Helper method, used by isPackTaskActive  and isBackupTaskActive.
            Returns 0 if task is dead, 1 if task is alive, but is assigned 
            to another App object, 2 if task is alive and is assigned 
            to App object with given URL.

            Arguments:

                'app_url' -- URL of the App object to check.
                'pack_task' -- if true, test pack task else test backup task.

            Result:

                0, 1 or 2.
        """
        if pack_task:
            task = self.pack_db_task_id
        else:
            task = self.backup_db_task_id

        if task is None:
            return 0

        if self.app_with_sceduler_URL is None:
            task = None
            return 0

        oldAppObject = self.unrestrictedTraverse( self.app_with_sceduler_URL, None )
        oldScheduler = oldAppObject is not None and getattr( oldAppObject, 'portal_scheduler', None ) or None

        if oldScheduler is None or oldScheduler.getScheduleElement(task) is None:
            task=None
            self.app_with_sceduler_URL = None
            return 0

        if self.app_with_sceduler_URL != app_url:
            return 1

        return 2

    def unregistryAppBackup( self, app_path ):
        """ 
            Clears pack and backup tasks ids if used portal_scheduler of App with path app_path.

            Prevent errors when add/remove sites.

            Arguments:

                'app_path' -- path to the site object to unregister 
                    (kill pack and backup tasks from portal_scheduler).
        """
        #todo: fix 'read only' error
        if self.app_with_sceduler_URL is not None and '/' + self.app_with_sceduler_URL == app_path:
            self.app_with_sceduler_URL = None
            self.backup_db_task_id = None
            self.pack_db_task_id = None

        self._p_changed = 1

    def manage_beforeDelete( self, item, container ):
        """
            Deletes tasks in portal_scheduler
        """
        if ( self.pack_db_task_id or self.backup_db_task_id ) and self.app_with_sceduler_URL:
            appObject = self.unrestrictedTraverse( self.app_with_sceduler_URL, None )
            scheduler = appObject is not None and getattr( appObject, 'portal_scheduler', None ) or None
            if scheduler is not None:
                scheduler.delScheduleElement( self.pack_db_task_id )
                scheduler.delScheduleElement( self.backup_db_task_id )

    def getNotifiedMembers( self ):
        """
            Returns list of notified members (admins)
        """
        if getattr(self, '_notified_members', None) is not None:
            return self._notified_members
        return []

    def sendBackupNotify( self, except_text='', info='' ):
        """
            Sends a notification
        """
        appObject = self.unrestrictedTraverse( self.app_with_sceduler_URL, None )
        try:
            msg = getToolByName( appObject, 'msg', None )
            lang = msg.get_default_language()
            if except_text.count('not created') != 0:
                except_text = except_text[0:except_text.index('not created')-1] + \
                              msg.gettext('not created', lang=lang)
            else:
                except_text = msg.gettext(except_text, lang=lang)

            appObject.MailHost.sendTemplate( \
                template='backup_notify',
                mto=self._notified_members, 
                lang=lang,
                except_text=except_text,
                info=info,
                date=DateTime().strftime('%d.%m.%Y %H:%M')
            )
        except:
            pass

def createBackupFSRoot( self, REQUEST=None ):
    """ 
        Creates the 'ExpressSuiteBackup' object (only one) of BackupFSRoot class
    """
    b = BackupFSRoot()
    if not hasattr(self, 'ExpressSuiteBackup'):
        self._setObject(b.id, b)
    if REQUEST:
        REQUEST['RESPONSE'].redirect( self.DestinationURL() + '/manage_main' )

def initialize( context ):
    context.registerClass(
    BackupFSRoot,
    #permission = 'Add BackupFSRoot',
    constructors = ( createBackupFSRoot, ))

InitializeClass( BackupFSRoot )
