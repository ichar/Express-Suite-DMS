//
// Selected combo-options
//
function upSelected( requested_users_id ) {
  var destList = window.document.all[requested_users_id];
  var len = destList.options.length;
  if( len == 0 ) return;

  if ( destList.options[0].selected != true ) {
    for( var i = 1; i < len; i++ ) {
      if ((destList.options[i] != null) && (destList.options[i].selected == true)) {
        bufText = destList.options[ i-1 ].text;
        bufValue = destList.options[ i-1 ].value;
        destList.options[ i-1 ].text = destList.options[i].text;
        destList.options[ i-1 ].value = destList.options[i].value;
        destList.options[ i ].text = bufText;
        destList.options[ i ].value = bufValue;
        destList.options[ i-1 ].selected = true;
        destList.options[ i ].selected = false;
      }
    }
  }
}

function downSelected( requested_users_id ) {
  var destList = window.document.all[requested_users_id];
  var len = destList.options.length;
  if( len == 0 ) return;

  if ( destList.options[ len-1 ].selected != true ) {
    for( var i = len; i >= 0; i-- ) {
      if ((destList.options[i] != null) && (destList.options[i].selected == true)) {
        bufText = destList.options[ i+1 ].text;
        bufValue = destList.options[ i+1 ].value;
        destList.options[ i+1 ].text = destList.options[i].text;
        destList.options[ i+1 ].value = destList.options[i].value;
        destList.options[ i ].text = bufText;
        destList.options[ i ].value = bufValue;
        destList.options[ i ].selected = false;
        destList.options[ i+1 ].selected = true;
      }
    }
  }
}

var color_block = '#FFFFFF';
var color_none = '#C9D3DC';

function TabDisplay( name, tab, mode ) {
  var x_display = ( mode=='none' ? 'none' : 'block' );
  var x_backgroundColor = ( mode=='none' ? color_none : color_block );
  var x_fontWeight = ( mode=='none' ? 'normal' : 'bold' );

  var users_obj = document.all[ name+'_selector_users_window' ];
  var groups_obj = document.all[ name+'_selector_groups_window' ];
  var departments_obj = document.all[ name+'_selector_departments_window' ];
  var tab_users = document.all[ name+'_tab_users' ];
  var tab_groups = document.all[ name+'_tab_groups' ];
  var tab_departments = document.all[ name+'_tab_departments' ];

  if( tab=='users' && typeof(tab_users)=='object' ) {
    users_obj.style.display = x_display;
    tab_users.style.backgroundColor = x_backgroundColor;
    tab_users.style.fontWeight = x_fontWeight;
  } else if( tab=='groups' && typeof(tab_groups)=='object' ) {
    groups_obj.style.display = x_display;
    tab_groups.style.backgroundColor = x_backgroundColor;
    tab_groups.style.fontWeight = x_fontWeight;
  } else if( tab=='departments' && typeof(tab_departments)=='object' ) {
    departments_obj.style.display = x_display;
    tab_departments.style.backgroundColor = x_backgroundColor;
    tab_departments.style.fontWeight = x_fontWeight;
  }
}

function x_selector( name, tab ) {
  var search_selector = document.all[ name+'_search_field_type' ];
  var selector = ( tab=='users' ? [false, true, true] : ( tab=='groups' ? [true, false, true] : [true, true, false] ) );

  if( typeof( search_selector ) == 'object' ) {
    search_selector.value = name+'_all_users';
    document.all[ name+'_selected_users' ].disabled = selector[0];
    document.all[ name+'_selected_groups' ].disabled = selector[1];
    document.all[ name+'_selected_departments' ].disabled = selector[2];
  }
}

function open_requsted_window( window_type, name ) {
  var mode = ( window_type == 'users' ? 1 : ( window_type == 'groups' ? 2 : 3 ) );
  var select_type = document.all.select_type;

  switch( mode ) {
  case 1:
      TabDisplay( name, 'users', 'block' );
      TabDisplay( name, 'groups', 'none' );
      TabDisplay( name, 'departments', 'none' );
      x_selector( name, 'users' );
      break;
  case 2:
      TabDisplay( name, 'users', 'none' );
      TabDisplay( name, 'groups', 'block' );
      TabDisplay( name, 'departments', 'none' );
      x_selector( name, 'groups' );
      break;
  case 3:
      TabDisplay( name, 'users', 'none' );
      TabDisplay( name, 'groups', 'none' );
      TabDisplay( name, 'departments', 'block' );
      x_selector( name, 'departments' );
      break;
  }
  select_type.value = mode;
}

function SearchString( str, selector ) {
    var strn=0, strl=0;
    //select must be sorted to make it nice work
    var name = selector.value;
    var sbox = document.all[ name ];
    if( typeof(sbox) != 'object' ) return;
    for (var i = 0; i < sbox.length; i++) {
      sbox.options[i].selected = false;
      var curl = 0;
      var inpStr = str.toUpperCase();
      var selStr = sbox.options[i].text.toUpperCase()
      for (var l = 0; l < str.length+1; l++){
    	curl = l;
    	if (inpStr.charAt(l) != selStr.charAt(l)) break;
      }
      if (curl > strl) { strl = curl; strn = i; }
    }
    if (!sbox.multiple || str.length) sbox.options[strn].selected = true;
}
