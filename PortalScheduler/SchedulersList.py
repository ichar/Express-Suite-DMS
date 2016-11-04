"""
Portal Scheduler. SchedulersList class
$Id: SchedulersList.py, v 1.0 2008/02/20 12:00:00 Exp $

*** Checked 26/05/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from types import StringType, TupleType
from persistent.list import PersistentList

from AccessControl import ClassSecurityInfo
from OFS.SimpleItem import SimpleItem
from Globals import InitializeClass, DTMLFile


class SchedulersList( SimpleItem ):
     """ Schedule list object, contains information about all schedulers in ZODB """

     manage_options = (
         {'label':'Schedule list', 'action':'manageSchedulersListForm'},
         {'label':'Security', 'action':'manage_access'},
         {'label':'Undo', 'action':'manage_UndoForm'},
         {'label':'Event catalog', 'action':'manageCatalogForm'},
     )

     security = ClassSecurityInfo()

     manageSchedulersListForm = DTMLFile('dtml/manageSchedulersList', globals())

     def __init__( self, id='SchedulersList', title="Schedulers list" ):
         self.id = id
         self.title = title
         self.paths = PersistentList()

     def registerScheduler( self, scheduler ):
         scheduler = self._getPath( scheduler )
             
         if not scheduler in self.paths:
             self.paths.append( scheduler )
             return 1

         return None

     def unregisterScheduler( self, scheduler ):
         scheduler = self._getPath( scheduler )
         try:
             self.paths.remove( scheduler )
             return 1
         except ValueError:
             return None

     security.declarePublic( 'listPaths' )
     def listPaths( self ):
         return self.paths

     def isRegistered( self, scheduler ):
         scheduler = self._getPath( scheduler )
         return scheduler in self.listPaths()
         
     security.declarePublic( 'listSchedulers' )
     def listSchedulers( self ):
         schedulers = []
         for path in list( self.paths ):
             schedule = self.unrestrictedTraverse( path , None )
             if schedule:
                 schedulers.append( schedule )
             else:
                 self.unregisterScheduler( path )
         return schedulers

     security.declarePublic('getUrlList')
     def getUrlList( self ):
         return self.listPaths()

     def _getPath( self, scheduler ):
         if type(scheduler) is StringType:
             return scheduler.split('/')
         elif type(scheduler) is TupleType:
             return scheduler
         else:
             return scheduler.getPhysicalPath()

InitializeClass( SchedulersList )


def createSchedulersList( self, REQUEST={} ):
    """ Create a new Schedule """
    ob = SchedulersList()
    self._setObject( ob.id, ob )

    if REQUEST:
        REQUEST['RESPONSE'].redirect( self.DestinationURL() + '/manage_main' )

def initialize( context ):
    context.registerClass(
              SchedulersList,
              permission = 'Add SchedulersList',
              constructors = (createSchedulersList, ))
