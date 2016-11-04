"""
Features are simplified interfaces used to describe class instances.
$Id: Features.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 04/03/2008 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from Interface import Base
from new import classobj as _classobj

class Feature( Base ): pass

class isAnObjectManager(Feature): pass
class isAttachment(Feature): pass
class isCategorial(Feature): pass
class isCompositeDocument(Feature): pass
class isContentStorage(Feature): pass
class isDocument(Feature): pass
class isFSFile(Feature): pass
class isFSFolder(Feature): pass
class isImage(Feature): pass
class isIncomingMailFolder(Feature): pass
class isLockable(Feature): pass
class isMailFolder(Feature): pass
class isOutgoingMailFolder(Feature): pass
class isPortalContent(Feature): pass
class isPortalRoot(Feature): pass
class isPrincipiaFolderish(Feature): pass
class isPrintable(Feature): pass
class isPublishable(Feature): pass
class isQuestionnaire(Feature): pass
class isSiteRoot(Feature): pass
class isSubscriptionRoot(Feature): pass
class isSyncableContent(Feature): pass
class isTaskItem(Feature): pass
class isVersion(Feature): pass
class isVersionable(Feature): pass

class canHaveSubfolders(Feature): pass

class hasContentFilter(Feature): pass
class hasLanguage(Feature): pass
class hasSubscription(Feature): pass

def createFeature( name ):
    """
        Creates a new feature with a given name.
    """
    try:
        feature = _classobj( name, (Feature,), {} )
    except SystemError: # python2.1
        exec 'class %s ( Feature ): pass' % name
        feature = locals()[ name ]
    globals()[ name ] = feature
    return feature
