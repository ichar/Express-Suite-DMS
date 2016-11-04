"""
Exception classes and support functions
$Id: Exceptions.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 26/05/2008 ***

"""
__version__ = "$Revision: 1.0 $"[11:-2]

import re, sys
from linecache import getline
from locale import Error as LocaleError
from traceback import format_exception, tb_lineno
from types import StringType, DictType, ListType, TupleType

from Acquisition import aq_inner, aq_parent, aq_base
from DocumentTemplate.DT_Util import TemplateDict
from OFS.CopySupport import CopyError
from zExceptions import Unauthorized

try:
    from webdav.Lockable import ResourceLockedError
except ImportError:
    class ResourceLockedError( Exception ): pass

try:
    from zExceptions.ExceptionFormatter import TextExceptionFormatter
except ImportError:
    TextExceptionFormatter = None

from Products.CMFCore.FSPythonScript import FSPythonScript
from Products.CMFCore.FSDTMLMethod import FSDTMLMethod

import Config, Utils
from DTMLTags import RevisionTag
from Products.PortalScheduler import Utils as SchedulerUtils

if TextExceptionFormatter is not None:

    class ExceptionFormatter( TextExceptionFormatter ):

        show_revisions = 1

        def formatLine( self, tb ):
            result = TextExceptionFormatter.formatLine( self, tb )
            sep = self.line_sep

            is_last = tb.tb_next is None
            f = tb.tb_frame
            co = f.f_code
            filename = co.co_filename
            lineno = tb_lineno(tb)

            if co.co_argcount:
                obj = f.f_locals.get( co.co_varnames[0], None )
                if isinstance( obj, FSDTMLMethod ):
                    result += '%s    DTML method %s, rev. %s, at %s' % \
                            ( sep, obj.getId(), getDTMLVersion(obj), obj.getObjectFSPath() )

                elif isinstance( obj, FSPythonScript ):
                    result += '%s    Python script %s, rev. %s, at %s' % \
                            ( sep, obj.getId(), getScriptVersion(obj), obj.getObjectFSPath() )

            line = getline( filename, lineno )
            if line:
                result += '%s    Line %d of function %s:%s      %s' % \
                          ( sep, lineno - co.co_firstlineno, co.co_name, sep, line.strip() )

            names = co.co_varnames[ :co.co_argcount ]
            if names:
                result += sep + '    Function arguments:'
                for name, value in listVariables( f.f_locals, names ):
                    result += sep + '      ' + name + '=' + value

            names = is_last and co.co_varnames[ co.co_argcount: ]
            if names:
                result += sep + '    Function variables:'
                for name, value in listVariables( f.f_locals, names ):
                    result += sep + '      ' + name + '=' + value

            return result

    _fmt = ExceptionFormatter( Config.MaxTracebackDepth )

    def formatException( *args ):
        t, v, tb = args or sys.exc_info()
        try: return '\n'.join( _fmt.formatException( t, v, tb ) )
        except: return '\n'.join( format_exception( t, v, tb ) )

else:
    # Zope < 2.6
    class ExceptionFormatter: pass
    def formatException( *args ): pass


#_exc_names = [ 'Debug Error', 'NotFound', 'BadRequest', 'InternalError', 'Forbidden' ]
_exc_types = [ Unauthorized ]
_dlg_rec = re.compile( r'<html\b[^>]*>.*?(?:<title>(.*?)</title>.*?)?<body\b[^>]*>(.*?)</body>.*?</html>' , re.I + re.S )
_pub_rec = re.compile( r'<table\b[^>]*>.*?<p><strong>(.*?)</strong></p>(.*?)<hr\b[^>]*>.*?</table>' , re.I + re.S )
_tag_rec = re.compile( r'<[^>]*>' )
_spc_rec = re.compile( r'\s+' )

def formatErrorValue( etype, value ):
    """
        Strips HTML tags from Zope error messages
    """
    if not ( type(etype) is StringType or etype in _exc_types ):
        return value

    if type(value) is StringType:
        message = value
    elif getattr( value, 'message', None ):
        message = str( value.message )
    else:
        return value

    match = _dlg_rec.search( message ) \
         or _pub_rec.search( message )

    if match:
        message = _tag_rec.sub( ' ', match.group(2) )
        message = _spc_rec.sub( ' ', message.strip() )
        if message.startswith( '! ' ):
            message = message[ 2: ]
        if not message:
            message = match.group(1)

    message = _tag_rec.sub( ' ', message )
    message = _spc_rec.sub( ' ', message.strip() )

    if type(value) is StringType:
        value = message
    else:
        value.message = message

    return value


def listVariables( namespace, names ):
    results = []

    for name in names:
        try:
            item = namespace[ name ]
        except KeyError:
            value = '<undefined>'
        else:
            value = getObjectRepr( item )
            path = getObjectPath( item, 0 )

            if path:
                context = getObjectPath( item, 1 )
                if context == path:
                    value += ' at %s' % path
                else:
                    value += ' at %s in context %s' % ( path, context )

            if isinstance( item, TemplateDict ):
                value += ' ' + formatTemplateDict( item )

        results.append( (name, value) )

    return results

def formatTemplateDict( md ):
    stack = []
    res = []

    while 1:
        try: item = md._pop()
        except IndexError: break
        stack.insert( 0, item )

        try: value = repr(item)
        except: value = '<unprintable %s object>' % type(item).__name__
        res.insert( 0, value )

    # restore dict
    for item in stack:
        md._push( item )

    return '[ ' + ', '.join(res) + ' ]'

_container_types = ( DictType, ListType, TupleType, )
MaxObjectReprLength = 200

def getObjectRepr( object ):
    # Returns simple *object* representation.
    object = aq_base(object)
    info = ''

    if type(object) in _container_types and len(object) > MaxObjectReprLength / 4:
        return '<large %s object: %d items>' % (type(object).__name__, len(object))

    try: info += repr(object)[ : MaxObjectReprLength ]
    except:
        try: info += '<unprintable %s object>' % object.__class__.__name__
        except: info += '<unprintable %s object>' % type(object).__name__

    try: info += ' [%s]' % object.getId()  # item-like
    except:
        try: info += ' <%d>' % object.getRID()  # catalog brains
        except:
            try: info += ' [%s]' % object.__name__   # all else
            except: pass

    return info

def getObjectPath( object, use_context=None ):
    # Returns *object* path, either containment or context.
    if aq_parent( object ) is None:
        return ''

    path = ['']

    while object is not None:
        base = aq_base( object )
        try:
            if base.isTopLevelPrincipiaApplicationObject:
                break
        except:
            pass

        # try hard to find object's ID
        try: id = base.getId()  # item-like
        except:
            try: id = '<%d>' % base.getRID()  # catalog brains
            except:
                try: id = base.__name__   # all else
                except: id = '<unknown>'  # no ID

        path.insert( 1, id )

        if use_context:
            object = aq_parent( object )
        else:
            object = aq_parent( aq_inner( object ) )

    try: return '/'.join( map( str, path ) )
    except: return 'broken path'

def getDTMLVersion( doc ):
    """
        Returns version string of the DTML document.
    """
    try:
        blocks = doc._v_blocks
    except AttributeError:
        return None

    for block in blocks[:5]:
        if isinstance( block, RevisionTag ):
            return block.version

    return None

def getScriptVersion( script ):
    """
        Returns version string of the Python script.
    """
    count = sol = 0

    while count < 5:
        try:
            eol = script._body.index( '\n', sol )
        except ValueError:
            return None
        line = script._body[ sol:eol ]

        if line.startswith('#'):
            try:
                line = line[ line.index('$'): ]
                if line.startswith('$Revision:'):
                    line = line[ :line.index('$',1)+1 ]
                    return line[ 11:-2 ]
            except ValueError:
                pass

        sol = eol+1
        count += 1

    return None


class ConverterError   ( Exception      ): pass
class SimpleError      ( Exception      ): pass
class InvalidIdError   ( SimpleError    ): pass
class ReservedIdError  ( InvalidIdError ): pass
class DuplicateIdError ( InvalidIdError ): pass

# XXX a hack to prevent circular import
Utils.InvalidIdError   = InvalidIdError
Utils.DuplicateIdError = DuplicateIdError

SchedulerUtils.InvalidIdError   = InvalidIdError
SchedulerUtils.DuplicateIdError = DuplicateIdError
