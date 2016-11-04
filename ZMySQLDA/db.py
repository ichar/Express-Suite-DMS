##############################################################################
# 
# Zope Public License (ZPL) Version 1.0
# -------------------------------------
# 
# Copyright (c) Digital Creations.  All rights reserved.
# 
# This license has been certified as Open Source(tm).
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
# 
# 1. Redistributions in source code must retain the above copyright
#    notice, this list of conditions, and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions, and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 
# 3. Digital Creations requests that attribution be given to Zope
#    in any manner possible. Zope includes a "Powered by Zope"
#    button that is installed by default. While it is not a license
#    violation to remove this button, it is requested that the
#    attribution remain. A significant investment has been put
#    into Zope, and this effort will continue if the Zope community
#    continues to grow. This is one way to assure that growth.
# 
# 4. All advertising materials and documentation mentioning
#    features derived from or use of this software must display
#    the following acknowledgement:
# 
#      "This product includes software developed by Digital Creations
#      for use in the Z Object Publishing Environment
#      (http://www.zope.org/)."
# 
#    In the event that the product being advertised includes an
#    intact Zope distribution (with copyright and license included)
#    then this clause is waived.
# 
# 5. Names associated with Zope or Digital Creations must not be used to
#    endorse or promote products derived from this software without
#    prior written permission from Digital Creations.
# 
# 6. Modified redistributions of any form whatsoever must retain
#    the following acknowledgment:
# 
#      "This product includes software developed by Digital Creations
#      for use in the Z Object Publishing Environment
#      (http://www.zope.org/)."
# 
#    Intact (re-)distributions of any official Zope release do not
#    require an external acknowledgement.
# 
# 7. Modifications are encouraged but must be packaged separately as
#    patches to official Zope releases.  Distributions that do not
#    clearly separate the patches from the original work must be clearly
#    labeled as unofficial distributions.  Modifications which do not
#    carry the name Zope may be packaged in any form, as long as they
#    conform to all of the clauses above.
# 
# 
# Disclaimer
# 
#   THIS SOFTWARE IS PROVIDED BY DIGITAL CREATIONS ``AS IS'' AND ANY
#   EXPRESSED OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#   fIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#   PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL DIGITAL CREATIONS OR ITS
#   CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#   SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#   LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
#   USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#   ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#   OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
#   OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
#   SUCH DAMAGE.
# 
# 
# This software consists of contributions made by Digital Creations and
# many individuals on behalf of Digital Creations.  Specific
# attributions are listed in the accompanying credits file.
# 
##############################################################################
"""
$Id: db.py,v 1.20 2002/03/14 20:24:54 adustman Exp $

*** Checked 31/03/2009 ***

"""
__version__='$Revision: 1.20 $'[11:-2]

import string, sys
from DateTime import DateTime
from zLOG import LOG, ERROR, INFO, DEBUG
from string import strip, split, find, upper, rfind
import time

from AccessControl.SecurityManagement import get_ident

import _mysql
from _mysql_exceptions import OperationalError, ProgrammingError, NotSupportedError
MySQLdb_version_required = (0,9,2)

_v = getattr(_mysql, 'version_info', (0,0,0))
if _v < MySQLdb_version_required:
    raise NotSupportedError, \
        "ZMySQLDA requires at least MySQLdb %s, %s found" % \
        (MySQLdb_version_required, _v)

from MySQLdb.converters import conversions
from MySQLdb.constants import FIELD_TYPE, CR, CLIENT
from Shared.DC.ZRDB.TM import TM

hosed_connection = (
    CR.SERVER_GONE_ERROR,
    CR.SERVER_LOST
    )

key_types = {
    "PRI": "PRIMARY KEY",
    "MUL": "INDEX",
    "UNI": "UNIQUE",
    }

field_icons = "bin", "date", "datetime", "float", "int", "text", "time"

icon_xlate = {
    "varchar": "text", "char": "text",
    "enum": "what", "set": "what",
    "double": "float", "numeric": "float",
    "blob": "bin", "mediumblob": "bin", "longblob": "bin",
    "tinytext": "text", "mediumtext": "text",
    "longtext": "text", "timestamp": "datetime",
    "decimal": "float", "smallint": "int",
    "mediumint": "int", "bigint": "int",
    }

type_xlate = {
    "double": "float", "numeric": "float",
    "decimal": "float", "smallint": "int",
    "mediumint": "int", "bigint": "int",
    "int": "int", "float": "float",
    "timestamp": "datetime", "datetime": "datetime",
    "time": "datetime",
    }
    
def _mysql_timestamp_converter(s):
    if len(s) < 14:
        s = s + "0"*(14-len(s))
        parts = map(int, (s[:4],s[4:6],s[6:8],
                          s[8:10],s[10:12],s[12:14]))
    return DateTime("%04d-%02d-%02d %02d:%02d:%02d" % tuple(parts))

def DateTime_or_None(s):
    try: return DateTime(s)
    except: return None

def int_or_long(s):
    try: return int(s)
    except: return long(s)

"""Locking strategy:

The minimum that must be done is a mutex around a query, store_result
sequence. When using transactions, the mutex must go around the
entire transaction."""

class DB( TM ):

    Database_Connection=_mysql.connect
    Database_Error=_mysql.Error

    defs={
        FIELD_TYPE.CHAR: "i", FIELD_TYPE.DATE: "d",
        FIELD_TYPE.DATETIME: "d", FIELD_TYPE.DECIMAL: "n",
        FIELD_TYPE.DOUBLE: "n", FIELD_TYPE.FLOAT: "n", FIELD_TYPE.INT24: "i",
        FIELD_TYPE.LONG: "i", FIELD_TYPE.LONGLONG: "l",
        FIELD_TYPE.SHORT: "i", FIELD_TYPE.TIMESTAMP: "d",
        FIELD_TYPE.TINY: "i", FIELD_TYPE.YEAR: "i",
        }

    conv=conversions.copy()
    conv[FIELD_TYPE.LONG] = int_or_long
    conv[FIELD_TYPE.DATETIME] = DateTime_or_None
    conv[FIELD_TYPE.DATE] = DateTime_or_None
    conv[FIELD_TYPE.DECIMAL] = float
    del conv[FIELD_TYPE.TIME]

    _p_oid = _p_changed = _registered=None
    _v_connected = None

    def _IsDebug( self ):
        try:
            return self.container.parent().getProperty('DEBUG_ZMySQLDA')
        except:
            return 0

    def __init__( self, connection=None, container=None ):
        self.connection = connection
        self.container = container
        self.db = None

        if connection:
            self.open( connection )

    def is_opened( self ):
        if self.db is not None:
            return self.db.open and 1 or 0
        return None

    def open( self, s=None ):
        # Open _mysql connection instance
        # -------------------------------
        from thread import allocate_lock
        if s:
            self.kwargs = self._parse_connection_string( s )
            self.connection = s
        if not self.connection:
            return

        self.db = apply(self.Database_Connection, (), self.kwargs)

        transactional = self.db.server_capabilities & CLIENT.TRANSACTIONS
        if self._try_transactions == '-':
            transactional = 0
        elif not transactional and self._try_transactions == '+':
            raise NotSupportedError, "transactions not supported by this server"
        self._use_TM = self._transactions = transactional

        if self._mysql_lock:
            self._use_TM = 1
        if self._use_TM:
            self._tlock = allocate_lock()
        self._lock = allocate_lock()

        self._v_connected = 1

        LOG("ZMySQLDA", DEBUG, "Open new connection, TID: %s, lock mode: [%s:%s:%s]" % ( \
            get_ident(), \
            self._transactions and 1 or 0, \
            self._mysql_lock and 1 or 0, \
            self._use_TM and 1 or 0, \
            ))

    def close( self ):
        # Close _mysql connection instance
        # --------------------------------
        if self.is_opened() and hasattr(self.db, 'close'):
            LOG("ZMySQLDA", DEBUG, "Close connection, TID: %s" % get_ident())
            self.db.close()

        self._v_connected = 0

    def __del__( self ):
        try:
            self.close()
            self.db = None
        except: pass

    def _parse_connection_string( self, connection ):
        kwargs = {'conv': self.conv}
        items = split(connection)
        self._use_TM = None
        if not items: return kwargs
        lockreq, items = items[0], items[1:]
        if lockreq[0] == "*":
            self._mysql_lock = lockreq[1:]
            db_host, items = items[0], items[1:]
            self._use_TM = 1
        else:
            self._mysql_lock = None
            db_host = lockreq
        if '@' in db_host:
            db, host = split(db_host,'@',1)
            kwargs['db'] = db
            if ':' in host:
                host, port = split(host,':',1)
                kwargs['port'] = int(port)
            kwargs['host'] = host
        else:
            kwargs['db'] = db_host
        if kwargs['db'] and kwargs['db'][0] in ('+', '-'):
            self._try_transactions = kwargs['db'][0]
            kwargs['db'] = kwargs['db'][1:]
        else:
            self._try_transactions = None
        if not kwargs['db']:
            del kwargs['db']
        if not items: return kwargs
        kwargs['user'], items = items[0], items[1:]
        if not items: return kwargs
        kwargs['passwd'], items = items[0], items[1:]
        if not items: return kwargs
        kwargs['unix_socket'], items = items[0], items[1:]
        return kwargs

    def tables( self, rdb=0, _care=('TABLE', 'VIEW') ):
        r=[]
        a=r.append
        self._lock.acquire()
        try:
            self.db.query("SHOW TABLES")
            result = self.db.store_result()
        finally:
            self._lock.release()
        row = result.fetch_row(1)
        while row:
            a({'TABLE_NAME': row[0][0], 'TABLE_TYPE': 'TABLE'})
            row = result.fetch_row(1)
        return r

    def columns( self, table_name ):
        from string import join
        try:
            try:
                self._lock.acquire()
                # Field, Type, Null, Key, Default, Extra
                self.db.query('SHOW COLUMNS FROM %s' % table_name)
                c = self.db.store_result()
            finally:
                self._lock.release()
        except:
            return ()
        r=[]
        for Field, Type, Null, Key, Default, Extra in c.fetch_row(0):
            info = {}
            field_default = Default and "DEFAULT %s"%Default or ''
            if Default: info['Default'] = Default
            if '(' in Type:
                end = rfind(Type,')')
                short_type, size = split(Type[:end],'(',1)
                if short_type not in ('set','enum'):
                    if ',' in size:
                        info['Scale'], info['Precision'] = map(int, split(size,',',1))
                    else:
                        info['Scale'] = int(size)
            else:
                short_type = Type
            if short_type in field_icons:
                info['Icon'] = short_type
            else:
                info['Icon'] = icon_xlate.get(short_type, "what")
            info['Name'] = Field
            info['Type'] = type_xlate.get(short_type,'string')
            info['Extra'] = Extra,
            info['Description'] = join([Type, field_default, Extra or '',
                                        key_types.get(Key, Key or ''),
                                        Null != 'YES' and 'NOT NULL' or '']),
            info['Nullable'] = (Null == 'YES') and 1 or 0
            if Key:
                info['Index'] = 1
            if Key == 'PRI':
                info['PrimaryKey'] = 1
                info['Unique'] = 1
            elif Key == 'UNI':
                info['Unique'] = 1
            r.append(info)
        return r

    def query( self, query_string, max_rows=1000 ):
        if not self.is_opened():
            return (),()

        self._use_TM and self._register()
        IsDebug = self._IsDebug()
        desc = None
        result = ()
        db = self.db
        p_header = "TID.%s ZMySQLDA" % get_ident()
        qs = ''

        try:
            self._lock.acquire()
            try:
                for qs in filter(None, map(strip, split(query_string, '|'))): #\0
                    items = [ upper(x) for x in split(qs, None) ]
                    qtype = items[0]
                    if qtype == 'SELECT' and max_rows and 'LIMIT' not in items and 'UPDATE' not in items:
                        qs = "%s LIMIT %d" % ( qs, max_rows )
                    if IsDebug:
                        LOG(p_header, DEBUG, "query: %s" % qs)

                    n = 0
                    while True:
                        try:
                            db.query(qs)
                            c = db.store_result()
                            break
                        except OperationalError, m:
                            if m[0] in ( 1205, 1213, ) and n < 3:
                                time.sleep( 1.0 )
                                n += 1
                                continue
                            if m[0] not in hosed_connection:
                                LOG(p_header, ERROR, "operational error: %s" % qs, error=sys.exc_info())
                            else:
                                LOG(p_header, INFO, "hosed connection (%s): %s" % ( m[0], qs ))
                            raise
                        except:
                            LOG(p_header, ERROR, "programming error: %s" % qs, error=sys.exc_info())
                            raise

                    if desc is not None:
                        if c and (c.describe() != desc):
                            raise 'Query Error', ( 'Multiple select schema are not allowed' )
                    if c:
                        desc = c.describe()
                        result = c.fetch_row(max_rows)
                    else:
                        desc = None

            finally:
                self._lock.release()
                    
        except OperationalError, m:
            if m[0] not in hosed_connection:
                LOG(p_header, ERROR, "query:\n%s" % query_string)
                raise
            # Hm. maybe the db is hosed.  Let's restart it.
            db = self.db = apply(self.Database_Connection, (), self.kwargs)
            return self.query( query_string, max_rows )

        if desc is None: return (),()

        items = []
        func = items.append
        defs = self.defs
        for d in desc:
            item = {'name' : d[0],
                    'type' : defs.get(d[1], "t"),
                    'width': d[2],
                    'null' : d[6]}
            func(item)
        return items, result

    def string_literal( self, s ): return self.db.string_literal(s)

    def _begin( self, *ignored ):
        p_header = "TID.%s ZMySQLDA" % get_ident()
        LOG(p_header, DEBUG, "begin transaction")

        self._tlock.acquire()
        try:
            if self._transactions:
                self.db.query("BEGIN")
                self.db.store_result()
            if self._mysql_lock:
                self.db.query("SELECT GET_LOCK('%s',0)" % self._mysql_lock)
                self.db.store_result()
        except Exception, m:
            if m[0] not in hosed_connection:
                LOG(p_header, ERROR, "exception during _begin", error=sys.exc_info())
            else:
                LOG(p_header, INFO, "hosed connection (%s): _begin" % m[0])
            if self._tlock.locked():
                self._tlock.release()
            raise

    def _finish( self, *ignored ):
        p_header = "TID.%s ZMySQLDA" % get_ident()

        try:
            try:
                if self._mysql_lock:
                    self.db.query("SELECT RELEASE_LOCK('%s')" % self._mysql_lock)
                    self.db.store_result()
                if self._transactions:
                    self.db.query("COMMIT")
                    self.db.store_result()
            except:
                LOG(p_header, ERROR, "exception during _finish", error=sys.exc_info())
                raise
        finally:
            if self._tlock.locked():
                self._tlock.release()

        LOG(p_header, DEBUG, "commit transaction")

    def _abort( self, *ignored ):
        p_header = "TID.%s ZMySQLDA" % get_ident()

        try:
            if self._mysql_lock:
                self.db.query("SELECT RELEASE_LOCK('%s')" % self._mysql_lock)
                self.db.store_result()
            if self._transactions:
                self.db.query("ROLLBACK")
                self.db.store_result()
            else:
                LOG(p_header, ERROR, "aborting when non-transactional")
        finally:
            if self._tlock.locked():
                self._tlock.release()

        LOG(p_header, DEBUG, "abort transaction")
