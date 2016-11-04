//
// $Id: cleanup.js,v 1.1.2.1.6.5.4.11 2005/02/22 10:04:21 $
// $Revision: 1.1.2.1.6.5.4.11 $
//
// *** Checked 11/07/2007 ***

var tags_and_attrs = {};
var stack = [];
var keys = [];
var TID = null;

var no_removed_tags = ['TH','TD'];

function TagHasIncludedAttrs( key ) {
  try { 
    var x = included_attrs[key];
    if( x[1] && ( x[0] || !IsKeepFormatting() ) ) return x[1];
  } 
  catch (error) {}
  return null;
}

function TagIsExist( key ) {
  for (var i = 0; i < keys.length; i++) {
    if( key == keys[i] ) return 1;
  }
  return 0;
}

function TagNotAllowedInside( key ) {
  if( !key ) return 1;
  try { 
    var x = not_allowed_inside[key]; 
    for (var i = 0; i < x.length; i++) {
      for (var j = stack.length; j >= 0 ; --j) {
        if( stack[j] == x[i] ) return 1;
      }
    }
  } 
  catch (error) {}
  return 0;
}

function CheckNotNestedTagIsOmitted( key ) {
  if( !key ) return 0;
  try { 
    var x = not_nested_tags[key];
    var last_tag = stack[stack.length-1];
    for (var i = 0; i < x.length; i++) {
      if( last_tag == x[i] ) return x[i];
    }
  }
  catch (error) {}
  return 0;
}

function AttrIsExist( key, attr ) {
  try {
    var attrs = tags_and_attrs[key];
    for (var i = 0; i < attrs.length; i++) {
      if( attr == attrs[i] ) return 1;
    }
  } 
  catch (error) {}
  return 0;
}

function NoRemovedTag( key ) {
  if( !key ) return 0;
  try {
    for (var i = 0; i < no_removed_tags.length; i++) {
      if( key == no_removed_tags[i] ) return 1;
    }
  } 
  catch (error) {}
  return 0;
}

function FormattingTag( key ) {
  if( !key ) return 0;
  try {
    for (var i = 0; i < formatting_tags.length; i++) {
      if( key == formatting_tags[i] ) return 1;
    }
  } 
  catch (error) {}
  return 0;
}

function FormattingAttr( key, attr ) {
  try {
    var attrs = formatting_attrs[key];
    for (var i = 0; i < attrs.length; i++) {
      if( attr == attrs[i] ) return 1;
    }
  } 
  catch (error) {}
  return 0;
}

function StyleAttr( key, item ) {
  try {
    var attrs = style_attrs[key];
    for (var i = 0; i < attrs.length; i++) {
      if( !item || item == attrs[i] ) return 1;
    }
  } 
  catch (error) {}
  return 0;
}

function HTMLCleanup( html, debug, soft_clear, keep_formatting, remove_empty ) {
  var lines = update_str.split('#');
  var re = new RegExp('\s* (\w*) \s*', 'g');

  if( debug ) keys_info.value = '';
  
  for (var i = 0; i < lines.length; i++) {
    lines[i] = lines[i].replace(re, "$1");
    if( !lines[i] ) continue;
    var attrs = lines[i].split(' ');
    try { 
      var key = attrs[0];
      tags_and_attrs[key] = attrs.slice(1); 
      keys[i] = key;
	} catch (error) { continue; }
    if( debug ) keys_info.value += key + ': ' + tags_and_attrs[key] + '\n';
  }
  
  if( !html ) return;
  var clean_html = html;
  var tag_pattern = /<(\/?)([\w\?\:]*)\s*?(.*?)>/ig;
  var attrs_pattern = /([a-zA-Z\-]+)\s*=\s*(?:([\"\'])(.*?)\2|([\w\-\.\%\#]+))/ig;
  var formatting_pattern = /([a-zA-Z\-]+)\s*\:([^\;]*)\;?/ig;
  var clean_pointer = 0;
  var offset = 0;
  var p = 0;

  do {
    var tag = tag_pattern.exec( html );
    if( !tag ) break;

    var tag_str = tag[0];
    var p_closing = tag[1];
    var key = tag[2].toUpperCase();
    var attrs_str = tag[3];

    offset = html.substr(p).indexOf(tag_str);

    if( offset && !keep_formatting ) {
      var context = replace_context( html.substr(p, offset) );
      clean_html = clean_html.substr( 0, clean_pointer ) + context + 
         clean_html.substr( clean_pointer+offset );
      clean_pointer += context.length;
    } else {
      clean_pointer += offset; 
    }

    p += offset;

    if( !TagIsExist(key) || ( !soft_clear && TagNotAllowedInside(key) ) ) {
      var tag_replace_str = "";
    } else if( FormattingTag(key) && !keep_formatting ) {
      var tag_replace_str = "";
    } else {
      var tag_replace_str = "<" + p_closing + key;

      if( !p_closing ) {
        if( x = CheckNotNestedTagIsOmitted(key) ) {
          tag_replace_str = "</" + x + ">" + tag_replace_str;
          stack = stack.slice(0,-1);
        }

        while (attrs_str) {
          var attrs = attrs_pattern.exec( attrs_str );
          if( !attrs ) break;

          var attr_str = attrs[0];
          var attr = attrs[1].toLowerCase();
          var p_comma = attrs[2];
          var value = ( p_comma ? attrs[3] : attrs[4] );

          if( !AttrIsExist(key, attr) ) {
            continue;
          } else if( value && FormattingAttr(key, attr) ) {
            if( !soft_clear && !keep_formatting ) continue;
          } else if( value && attr == 'style' ) {
            if( !keep_formatting ) continue;
            attrs_replaced_value = '';

            while (true) {
              var x = formatting_pattern.exec( value );
              if( !x ) break;

              var x_str = x[0];
              var item = x[1].toLowerCase();
              var x_value = x[2];
                
              if( !StyleAttr(key, item) ) continue;
              attrs_replaced_value += item + ':' + x_value + ';';
            }
            value = attrs_replaced_value;
            if( !value ) continue;
          }

          if( value ) {
            tag_replace_str += ' ' + attr + '="' + value + '"';
          } else {
            tag_replace_str += ' ' + attr;
          }
        }

        include_str = TagHasIncludedAttrs(key);
        if( include_str ) tag_replace_str += ' ' + include_str;
      }
      tag_replace_str += ">";

      var n = stack.length-1;
      if( p_closing && stack[n] == key ) stack = stack.slice(0,-1);
      else stack[++n] = key;
    }

    clean_html = clean_html.substr( 0, clean_pointer ) + tag_replace_str + 
         clean_html.substr( clean_pointer+tag_str.length );

    clean_pointer += tag_replace_str.length;
    p += tag_str.length;

    if( debug ) { 
      stack_info.value = stack;
      interrupt(0);
    }

  } while (html);

  if( remove_empty ) {
    var found;
    do {
      var empty_tag_pattern = /(?:<([\w\?\:]*)(\s*[^>]*?>|>)(\s*?)<\/\1>)/ig;
      found = 0;
      while (true) {
        var tag = empty_tag_pattern.exec( clean_html );
        if( !tag ) break;
        if( NoRemovedTag( tag[1] ) ) continue;
        clean_html = clean_html.replace( tag[0], '' );
        found = 1;
      }
    } while (found)
  }

  return clean_html;
}

function replace_context( s ) {
  s = s.replace(/(&nbsp;| |\f|\r|\t|\v)+/g, ' ');
  s = s.replace(/ - /g, '&nbsp;-&nbsp;');
  s = s.replace(/^(-|°|¤|·|–|—|&deg;|&ordm;|&curren;|&middot;|&ndash;|&mdash;)\s+/g, '$1&nbsp;');
  s = s.replace(/^([\d\.]+)[ ]+(\S)/ig, "$1&nbsp;$2");
  return s;
}

function interrupt( mode ) {
  if( mode == 1 ) {
    window.clearTimeout( TID );
    return;
  } else {
    TID = window.setTimeout("interrupt(1)", 100);
  }
}
