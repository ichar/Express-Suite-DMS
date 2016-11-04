
""" Checked 21/11/2008 """

import sys, os
from DateTime import DateTime 

def cp_file(path_from, path_to):
    if os.name=='posix':
        command = 'cp '+path_from+' '+ path_to
    else:
        command = 'copy "'+path_from+'" "'+ path_to+'"'
    if os.system(command):
        raise 'Error while copying file'

def mv_file(path_from, path_to):
    if os.name=='posix':
        command = 'mv '+path_from+' '+ path_to
    else:
        command = 'move "'+path_from+'" "'+ path_to+'"'
    if os.system(command):
        raise 'Error while moving file'

def rm_folder(path):
    if os.name=='posix':
        command = 'rm -dr '+path
    else:
        command = 'rmdir /s /q "'+path+'"'
    if os.system(command):
        raise 'Error while removing folder'

def backup_fs(num_copies, backup_path='', arc_program_data=('', ''), connection=None):
    #function for backup FileStorage
    archive_by = arc_program_data[0]
    if not archive_by:
        return

    _from, name = os.path.split( connection.db().getName() )
    _p = backup_path and os.path.normpath( backup_path ) or _from

    if not os.access(_p, os.F_OK|os.W_OK):
        raise 'BError', 'Destination path inaccessible'

    now = DateTime().strftime('%Y%m%d')
    c = '.'

    file_extension = arc_program_data[1] or 'backup'
    backup_name = name + c + 'backup'

    try: instance = arc_program_data[1].split(c)[0] or ''
    except: instance = ''

    _to = '%s%s%s' % ( _p, os.sep, '0' )

    source_from    = _from + os.sep + name
    source_to      = _to   + os.sep + backup_name
    zodb_archive   = _to   + os.sep + name     + c + now + c + file_extension
    mysql_archive  = _to   + os.sep + instance + c + now + c + 'sql'

    #create archive folder
    CD = 'mkdir %s' % _to
    code = os.system( CD )
    if code:
        raise 'BError', 'Error while creating directory, exit code: %s' % code

    #copy database
    cp_file(source_from, source_to)

    #make zodb archive
    if os.name == 'posix':
        CZ = 'cd %s; %s %s %s' % ( _to, archive_by, zodb_archive, backup_name )
    else:
        CZ = '%s %s %s' % ( archive_by, zodb_archive, source_to )
    code = os.system( CZ )
    if code:
        raise 'BError', 'Error while make ZODB archive, exit code: %s, CZ: %s' % ( code, CZ )

    #make mysql dump
    if instance:
        if os.name == 'posix':
            CS = 'cd %s; mysqldump -u root --opt %s > %s' % ( _to, instance, mysql_archive )
        else:
            CS = 'mysqldump -u root --opt %s > %s' % ( instance, mysql_archive )
        code = os.system( CS )
        if code:
            raise 'BError', 'Error while dump MySQL database, exit code: %s, CS: %s' % ( code, CS )

    #remove database
    os.remove(source_to)

    temp = '%s%s%s' % ( _p, os.sep, '%s' )

    #remove oldest copy and swap others
    old = temp % `num_copies`
    if os.path.isdir( old ):
        #os.system( 'rm -dr %s' % old )
        rm_folder( old )

    for i in range(num_copies, 1, -1):
        if os.path.isdir( temp % `i-1` ):
            mv_file( temp % `i-1`, temp % `i` )

    mv_file(_to, temp % '1')
