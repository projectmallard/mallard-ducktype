# Copyright (c) 2014 Shaun McCance <shaunm@gnome.org>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import os
import sys

from . import entities


def FIXME(msg=None):
    if msg is not None:
        print('FIXME: %s' % msg)
    else:
        print('FIXME')

def _escape_xml_attr(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')

def _escape_xml(s):
    return s.replace('&', '&amp;').replace('<', '&lt;')

_escaped_chars = '$*=-@[]()"\''


class Attributes:
    def __init__(self):
        self._attrlist = []
        self._attrvals = {}

    def add_attribute(self, key, value):
        if key not in self._attrlist:
            self._attrlist.append(key)
        if key == 'style':
            self._attrvals.setdefault(key, [])
            self._attrvals[key].append(value)
        else:
            self._attrvals[key] = value

    def __contains__(self, item):
        return item in self._attrlist

    def _write_xml(self, fd):
        for attr in self._attrlist:
            fd.write(' ' + attr + '="')
            if attr == 'style':
                fd.write(' '.join([_escape_xml_attr(s) for s in self._attrvals[attr]]))
            else:
                fd.write(_escape_xml_attr(self._attrvals[attr]))
            fd.write('"')


class Directive:
    def __init__(self, name):
        self.name = name
        self.values = []
        self._dict = {}

    def add_value(self, name, value=None):
        if value is None:
            self.values.append(name)
        else:
            self.values.append((name, value))
            self._dict[name] = value


class Node:
    def __init__(self, name, outer=0, inner=None, linenum=0):
        self.name = name
        self.outer = outer
        if inner is None:
            self.inner = outer
        else:
            self.inner = inner
        self.info = None
        self.children = []
        self.attributes = None
        self.division = (name in ('page', 'section'))
        self.verbatim = (name in ('screen', 'code'))
        self.list = (name in ('list', 'steps', 'terms', 'tree'))
        self.terminal = (name in
                         ('p', 'screen', 'code', 'title',
                          'subtitle', 'desc', 'cite',
                          'name', 'email'))
        self.linenum = linenum
        self._namespaces = []
        self._parent = None
        self._depth = 1
        self._softbreak = False # Help keep out pesky trailing newlines

    @property
    def empty(self):
        return len(self.children) == 0 and self.info is None

    @property
    def available(self):
        if len(self.children) == 0:
            return True
        elif len(self.children) == 1:
            return self.children[0].name == 'title'
            # FIXME: desc, cite, subtitle?
        else:
            return False

    @property
    def depth(self):
        return self._depth

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, node):
        self._parent = node
        self._depth = node._depth + 1

    def add_child(self, child):
        if self._softbreak:
            self.children[-1] += '\n'
            self._softbreak = False
        self.children.append(child)
        child.parent = self

    def add_text(self, text):
        if self._softbreak:
            self.children[-1] += '\n'
            self._softbreak = False
        if text.endswith('\n'):
            text = text[:-1]
            self._softbreak = True
        if len(self.children) > 0 and isinstance(self.children[-1], str):
            self.children[-1] += text
        else:
            self.children.append(text)

    def add_namespace(self, prefix, uri):
        self._namespaces.append((prefix, uri))

    def write_xml(self, outfile=None):
        close = False
        if outfile is None:
            fd = sys.stdout
        elif isinstance(outfile, str):
            close = True
            fd = open(outfile, 'w')
        else:
            fd = outfile
        self._write_xml(fd)
        if close:
            fd.close()

    def _write_xml(self, fd, *, depth=0, verbatim=False):
        verbatim = verbatim or self.verbatim
        if self.name == 'page':
            fd.write('<?xml version="1.0" encoding="utf-8"?>\n')
        if not isinstance(self, Inline):
            fd.write(' ' * depth)
        fd.write('<' + self.name)
        if self.name == 'page':
            fd.write(' xmlns="http://projectmallard.org/1.0/"')
        for prefix, uri in self._namespaces:
            fd.write(' xmlns:' + prefix + '="' + uri + '"')
        if self.attributes is not None:
            self.attributes._write_xml(fd)
        if self.empty:
            if isinstance(self, Inline):
                fd.write('/>')
            else:
                fd.write('/>\n')
        elif (self.info is not None or
              isinstance(self.children[0], Block) or
              isinstance(self.children[0], Info) ):
            fd.write('>\n')
        else:
            fd.write('>')
        if self.info is not None:
            self.info._write_xml(fd, depth=depth+1)
        for i in range(len(self.children)):
            child = self.children[i]
            if isinstance(child, Inline):
                child._write_xml(fd, depth=depth, verbatim=verbatim)
            elif isinstance(child, Node):
                child._write_xml(fd, depth=depth+1, verbatim=verbatim)
            elif '\n' in child:
                nl = child.find('\n')
                while nl >= 0:
                    if nl + 1 == len(child) and i + 1 == len(self.children):
                        fd.write(_escape_xml(child[:nl]))
                    elif verbatim or (nl + 1 < len(child) and child[nl + 1] == '\n'):
                        fd.write(_escape_xml(child[:nl]) + '\n')
                    else:
                        fd.write(_escape_xml(child[:nl]) + '\n' + (' ' * depth))
                    child = child[nl + 1:]
                    nl = child.find('\n')
                if child != '':
                    fd.write(_escape_xml(child))
            else:
                fd.write(_escape_xml(child))
        if not self.empty:
            if isinstance(self, Inline):
                fd.write('</' + self.name + '>')
            elif self.terminal:
                fd.write('</' + self.name + '>\n')
            else:
                fd.write((' ' * depth) + '</' + self.name + '>\n')


class Block(Node):
    pass


class Info(Node):
    pass


class Inline(Node):
    pass


class SyntaxError(Exception):
    def __init__(self, message, parser):
        self.message = message
        self.parser = parser
        self.filename = parser.filename
        self.linenum = parser.linenum


class InlineParser:
    def __init__(self, parent, linenum=1):
        # Dummy node just to hold children while we parse
        self.current = Inline('_')
        self.filename = parent.filename
        self.linenum = linenum
        self._parent = parent

    def lookup_entity(self, entity):
        return self._parent.lookup_entity(entity)

    def parse_text(self, text):
        self._parse_text(text)
        while self.current.parent is not None:
            self.current = self.current.parent
        return self.current.children

    def _parse_text(self, text):
        start = cur = 0
        while cur < len(text):
            if self.current.parent is not None and text[cur] == ')':
                self.current.add_text(text[start:cur])
                self.current = self.current.parent
                cur += 1
                start = cur
            elif cur == len(text) - 1:
                cur += 1
                self.current.add_text(text[start:cur])
            elif text[cur] == '$' and text[cur + 1] in _escaped_chars:
                self.current.add_text(text[start:cur])
                self.current.add_text(text[cur + 1])
                cur += 2
                start = cur
            elif text[cur] == '$' and _isnmtoken(text[cur + 1]):
                end = cur + 1
                while end < len(text):
                    if not _isnmtoken(text[end]):
                        break
                    end += 1
                if end == len(text):
                    self.current.add_text(text[start:end])
                    cur = end
                elif text[end] == ';':
                    self.current.add_text(text[start:cur])
                    entname = text[cur + 1:end]
                    entval = self._parent.lookup_entity(entname)
                    if entval is not None:
                        self.current.add_text(entval)
                    else:
                        raise SyntaxError('Unrecognized entity: ' + entname, self)
                    start = cur = end + 1
                elif text[end] == '[':
                    self.current.add_text(text[start:cur])
                    node = Inline(text[cur + 1:end])
                    self.current.add_child(node)
                    attrparser = AttributeParser(self)
                    attrparser.parse_line(text[end + 1:])
                    if not attrparser.finished:
                        # We know we have all the text there could be,
                        # so this an unclosed attribute list. Do we make
                        # that an error, auto-close, or decide this was
                        # never really markup after all?
                        FIXME('unclosed attribute list')
                    node.attributes = attrparser.attributes
                    self.linenum = attrparser.linenum
                    start = cur = len(text) - len(attrparser.remainder)
                    if cur < len(text) and text[cur] == '(':
                        self.current = node
                        start = cur = cur + 1
                elif text[end] == '(':
                    self.current.add_text(text[start:cur])
                    node = Inline(text[cur + 1:end])
                    self.current.add_child(node)
                    self.current = node
                    start = cur = end + 1
                else:
                    cur = end
            else:
                if text[cur] == '\n':
                    self.linenum += 1
                cur += 1



class AttributeParser:
    def __init__(self, parent):
        self.remainder = None
        self.attributes = Attributes()
        self.finished = False
        self.filename = parent.filename
        self.linenum = parent.linenum
        self._quote = None
        self._value = ''
        self._attrname = None
        self._parent = parent

    def parse_value(self, text):
        retval = ''
        start = cur = 0
        while cur < len(text):
            if text[cur] == '$':
                if cur == len(text) - 1:
                    cur += 1
                    retval += text[start:cur]
                    start = cur
                elif text[cur] == '$' and text[cur + 1] in _escaped_chars:
                    retval += text[start:cur]
                    retval += text[cur + 1]
                    cur += 2
                    start = cur
                elif text[cur] == '$' and _isnmtoken(text[cur + 1]):
                    end = cur + 1
                    while end < len(text):
                        if not _isnmtoken(text[end]):
                            break
                        end += 1
                    if end == len(text):
                        retval += text[start:end]
                        start = cur = end
                    elif text[end] == ';':
                        retval += text[start:cur]
                        start = cur
                        entname = text[cur + 1:end]
                        entval = self._parent.lookup_entity(entname)
                        if entval is not None:
                            retval += entval
                        else:
                            raise SyntaxError('Unrecognized entity: ' + entname, self)
                        start = cur = end + 1
                    else:
                        cur = end
                else:
                    cur += 1
            else:
                if text[cur] == '\n':
                    self.linenum += 1
                cur += 1
        if cur != start:
            retval += text[start:cur]
        return retval

    def parse_line(self, line):
        i = 0
        while i < len(line) and not self.finished:
            if self._quote is not None:
                j = i
                while j < len(line):
                    if line[j] == '$':
                        # Will be parsed later. Just skip the escaped quote
                        # char so it doesn't close the attribute value.
                        if j + 1 < len(line) and line[j] in _escaped_chars:
                            j += 2
                        else:
                            j += 1
                    elif line[j] == self._quote:
                        self._value += line[i:j]
                        self._value = self.parse_value(self._value)
                        self.attributes.add_attribute(self._attrname, self._value)
                        self._value = ''
                        self._quote = None
                        i = j
                        break
                    else:
                        j += 1
                i += 1
            elif line[i].isspace():
                if line[i] == '\n':
                    self.linenum += 1
                i += 1
            elif line[i] == ']':
                self.finished = True
                self.remainder = line[i + 1:]
            elif line[i] in ('.', '#', '>'):
                j = i + 1
                while j < len(line):
                    if line[j].isspace() or line[j] == ']':
                        break
                    j += 1
                word = self.parse_value(line[i + 1:j])
                if line[i] == '>':
                    if line[i + 1] == '>':
                        self.attributes.add_attribute('href', word[1:])
                    else:
                        self.attributes.add_attribute('xref', word)
                elif line[i] == '.':
                    self.attributes.add_attribute('style', word)
                else:
                    self.attributes.add_attribute('id', word)
                i = j
            else:
                j = i
                while j < len(line) and _isnmtoken(line[j]):
                    j += 1
                word = line[i:j]
                if line[j] == '=' and word != '':
                    if line[j + 1] in ('"', "'"):
                        self._quote = line[j + 1]
                        self._value = ''
                        i = j + 2
                        self._attrname = word
                    else:
                        k = j + 1
                        while k < len(line):
                            if line[k].isspace() or line[k] == ']':
                                break
                            k += 1
                        value = self.parse_value(line[j + 1:k])
                        self.attributes.add_attribute(word, value)
                        i = k
                elif line[j].isspace() or line[j] == ']':
                    value = self.parse_value(line[i:j])
                    self.attributes.add_attribute('type', value)
                    i = j
                else:
                    raise SyntaxError('Invalid character in attribute list', self)


class DirectiveParser:
    def __init__(self, parent):
        self.remainder = None
        self.finished = False
        self.filename = parent.filename
        self.linenum = parent.linenum
        self.directive = None
        self._quote = None
        self._value = ''
        self._attrname = None
        self._parent = parent

    def parse_line(self, line):
        i = 0
        if self.directive is None:
            i = 2
            while i < len(line):
                if line[i].isspace():
                    break
                if line[i:i + 2] == ']]':
                    self.finished = True
                    self.remainder = line[i + 2:]
                    break
                i += 1
            if i == 2:
                raise SyntaxError('Directive must start with a name', self)
            self.directive = Directive(line[2:i])
        while i < len(line) and not self.finished:
            if self._quote is not None:
                j = i
                while j < len(line):
                    if line[j] == '$':
                        # Will be parsed later. Just skip the escaped quote
                        # char so it doesn't close the attribute value.
                        if j + 1 < len(line) and line[j] in _escaped_chars:
                            j += 2
                        else:
                            j += 1
                    elif line[j] == self._quote:
                        self._value += line[i:j]
                        if self._attrname is not None:
                            self.directive.add_value(self._attrname, self._value)
                        else:
                            self.directive.add_value(self._value)
                        self._attrname = None
                        self._value = ''
                        self._quote = None
                        i = j
                        break
                    else:
                        j += 1
                i += 1
            elif line[i].isspace():
                if line[i] == '\n':
                    self.linenum += 1
                i += 1
            elif line[i:i + 2] == ']]':
                self.finished = True
                self.remainder = line[i + 2:]
            else:
                j = i
                while j < len(line) and not self.finished:
                    if line[j:j + 2] in ('="', "='"):
                        self._quote = line[j + 1]
                        self._value = ''
                        self._attrname = line[i:j]
                        i = j + 2
                        break
                    elif line[j] == '=':
                        k = j + 1
                        while k < len(line):
                            if line[k].isspace():
                                break
                            if line[k:k + 2] == ']]':
                                self.finished = True
                                self.remainder = line[k + 2:]
                                break
                            k += 1
                        self.directive.add_value(line[i:j], line[j + 1:k])
                        i = k
                        break
                    elif line[j:j + 2] == ']]':
                        self.finished = True
                        self.remainder = line[j + 2:]
                        self.directive.add_value(line[i:j])
                    elif line[j].isspace() :
                        self.directive.add_value(line[i:j])
                        i = j
                        break
                    j += 1


class DuckParser:
    STATE_START = 1
    STATE_TOP = 2
    STATE_HEADER = 3
    STATE_HEADER_POST = 4
    STATE_SUBHEADER = 5
    STATE_SUBHEADER_POST = 6
    STATE_HEADER_ATTR = 7
    STATE_HEADER_ATTR_POST = 8
    STATE_HEADER_INFO = 9
    STATE_BLOCK = 10
    STATE_BLOCK_ATTR = 11
    STATE_BLOCK_READY = 12
    STATE_BLOCK_INFO = 13

    INFO_STATE_NONE = 101
    INFO_STATE_INFO = 102
    INFO_STATE_READY = 103
    INFO_STATE_BLOCK = 104
    INFO_STATE_ATTR = 105

    def __init__(self):
        self.state = DuckParser.STATE_START
        self.info_state = DuckParser.INFO_STATE_NONE
        self.document = Block('page')
        self.current = self.document
        self.curinfo = None
        self.linenum = 0
        self._value = ''
        self._attrparser = None
        self._directiveparser = None
        self._defaultid = None

    def lookup_entity(self, entity):
        if entity in entities.entities:
            return entities.entities[entity]
        else:
            # Try to treat it as a hex numeric reference
            hexnum = 0
            for c in entity:
                if c in '0123456789':
                    hexnum = hexnum * 16 + (ord(c) - 48)
                elif c in 'abcdef':
                    hexnum = hexnum * 16 + (ord(c) - 87)
                elif c in 'ABCDEF':
                    hexnum = hexnum * 16 + (ord(c) - 55)
                else:
                    hexnum = None
                    break
            if hexnum is not None:
                return chr(hexnum)
        return None

    def parse_file(self, filename):
        self.filename = filename
        self._defaultid = os.path.basename(filename)
        if self._defaultid.endswith('.duck'):
            self._defaultid = self._defaultid[:-5]
        fd = open(filename)
        for line in fd:
            self.parse_line(line)
        fd.close()

    def parse_line(self, line):
        self.linenum += 1
        self._parse_line(line)

    def parse_inline(self, node=None):
        if node is None:
            node = self.document
        newchildren = []
        for child in node.children:
            if isinstance(child, str):
                parser = InlineParser(self, linenum=node.linenum)
                newchildren.extend(parser.parse_text(child))
            else:
                self.parse_inline(child)
                newchildren.append(child)
        node.children = newchildren

    def finish(self):
        if (self.state in (DuckParser.STATE_HEADER_ATTR, DuckParser.STATE_BLOCK_ATTR) or
            self.info_state == DuckParser.INFO_STATE_ATTR):
            raise SyntaxError('Unterminated block declaration', self)
        self._push_value()
        if self._defaultid is not None:
            if self.document.attributes is None:
                self.document.attributes = Attributes()
            if 'id' not in self.document.attributes:
                self.document.attributes.add_attribute('id', self._defaultid)
        self.parse_inline()

    def _parse_line(self, line):
        if self._directiveparser is not None:
            self._parse_line_directive(line)
        elif self.info_state == DuckParser.INFO_STATE_INFO:
            self._parse_line_info(line)
        elif self.info_state == DuckParser.INFO_STATE_READY:
            self._parse_line_info(line)
        elif self.info_state == DuckParser.INFO_STATE_BLOCK:
            self._parse_line_info(line)
        elif self.info_state == DuckParser.INFO_STATE_ATTR:
            self._parse_line_info_attr(line)
        elif self.state == DuckParser.STATE_START:
            self._parse_line_top(line)
        elif self.state == DuckParser.STATE_TOP:
            self._parse_line_top(line)
        elif self.state == DuckParser.STATE_HEADER:
            self._parse_line_header(line)
        elif self.state == DuckParser.STATE_HEADER_POST:
            self._parse_line_header_post(line)
        elif self.state == DuckParser.STATE_SUBHEADER:
            self._parse_line_subheader(line)
        elif self.state == DuckParser.STATE_SUBHEADER_POST:
            self._parse_line_subheader_post(line)
        elif self.state == DuckParser.STATE_HEADER_ATTR:
            self._parse_line_header_attr(line)
        elif self.state == DuckParser.STATE_HEADER_ATTR_POST:
            self._parse_line_header_attr_post(line)
        elif self.state == DuckParser.STATE_BLOCK:
            self._parse_line_block(line)
        elif self.state == DuckParser.STATE_BLOCK_ATTR:
            self._parse_line_block_attr(line)
        elif self.state == DuckParser.STATE_BLOCK_READY:
            self._parse_line_block_ready(line)
        else:
            FIXME('unknown state')

    def _parse_line_top(self, line):
        if line.strip() == '':
            self.state = DuckParser.STATE_TOP
        elif line.startswith('[['):
            self._directiveparser = DirectiveParser(self)
            self._parse_line_directive(line)
        elif line.startswith('= '):
            self._value = line[2:]
            node = Block('title', 0, 2, linenum=self.linenum)
            self.current.add_child(node)
            self.current = node
            self.state = DuckParser.STATE_HEADER
        else:
            raise SyntaxError('Missing page header', self)

    def _parse_line_directive(self, line):
        self._directiveparser.parse_line(line)
        if self._directiveparser.finished:
            directive = self._directiveparser.directive
            self._directiveparser = None
            if directive.name.startswith('duck/'):
                if self.state != DuckParser.STATE_START:
                    raise SyntaxError('Ducktype declaration must be first', self)
                if directive.name != 'duck/1.0':
                    raise SyntaxError(
                        'Unsupported ducktype version ' + directive.name ,
                        self)
                for value in directive.values:
                    if isinstance(value, str):
                        raise SyntaxError(
                            'Unsupported ducktype extension ' + value,
                            self)
                    elif value[0] == 'encoding':
                        FIXME('encoding')
                    else:
                        raise SyntaxError(
                            'Unsupported ducktype extension ' + value[0],
                            self)
            elif directive.name == 'duck:ns':
                for value in directive.values:
                    if isinstance(value, str):
                        raise SyntaxError(
                            'Non-attribute value in namespace declaration',
                            self)
                    self.current.add_namespace(value[0], value[1])
            else:
                # FIXME: unknown directive
                pass
            if self.state == DuckParser.STATE_START:
                self.state == DuckParser.STATE_TOP

    def _parse_line_header(self, line):
        indent = self._get_indent(line)
        iline = line[indent:]
        if iline.startswith('@'):
            self._push_value()
            self.current = self.current.parent
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        elif indent >= self.current.inner:
            self._parse_line_header_attr_start(line)
        else:
            self._push_value()
            self.current = self.current.parent
            self.state = DuckParser.STATE_HEADER_POST
            self._parse_line(line)

    def _parse_line_header_post(self, line):
        if line.startswith(('-' * self.current.depth) + ' '):
            self._value = line[self.current.depth + 1:]
            node = Block('subtitle', 0, self.current.depth + 1, linenum=self.linenum)
            self.current.add_child(node)
            self.current = node
            self.state = DuckParser.STATE_SUBHEADER
        elif line.lstrip().startswith('@'):
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_subheader(self, line):
        indent = self._get_indent(line)
        iline = line[indent:]
        if iline.startswith('@'):
            self._push_value()
            self.current = self.current.parent
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        elif indent >= self.current.inner:
            self._parse_line_header_attr_start(line)
        else:
            self._push_value()
            self.current = self.current.parent
            self.state = DuckParser.STATE_SUBHEADER_POST
            self._parse_line(line)

    def _parse_line_subheader_post(self, line):
        if line.lstrip().startswith('@'):
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_header_attr_start(self, line):
        iline = line[self.current.inner:]
        if iline.startswith('['):
            self._push_value()
            self.current = self.current.parent
            self._attrparser = AttributeParser(self)
            self._attrparser.parse_line(iline[1:])
            if self._attrparser.finished:
                self.current.attributes = self._attrparser.attributes
                self.state = DuckParser.STATE_HEADER_ATTR_POST
                self._attrparser = None
            else:
                self.state = DuckParser.STATE_HEADER_ATTR
        else:
            self._value += line[self.current.inner:]

    def _parse_line_header_attr(self, line):
        self._attrparser.parse_line(line)
        if self._attrparser.finished:
            self.current.attributes = self._attrparser.attributes
            self.state = DuckParser.STATE_HEADER_ATTR_POST
            self._attrparser = None

    def _parse_line_header_attr_post(self, line):
        if line.lstrip().startswith('@'):
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_info(self, line):
        if line.strip() == '':
            # If the info elements weren't indented past the indent
            # level of the parent and the parent is a block, blank
            # line terminates info, because it must terminate the
            # block according to block processing rules.
            if (self.current.outer == self.current.inner and not self.current.division):
                self._push_value()
                self.info_state = DuckParser.INFO_STATE_NONE
                self._parse_line(line)
                return
            # If we're inside a leaf element like a paragraph, break
            # out of that. Unless it's an indented verbatim element,
            # in which case the newline is just part of the content.
            if self.curinfo.terminal:
                if (self.curinfo.verbatim and
                    self.curinfo.inner > self.curinfo.outer):
                    self._value += '\n'
                else:
                    self._push_value()
                    self.curinfo = self.curinfo.parent
                    self.info_state = DuckParser.INFO_STATE_INFO
            return

        indent = self._get_indent(line)
        if self.current.info is None:
            self.current.info = Block('info', indent, indent, linenum=self.linenum)
            self.curinfo = self.current.info
        if indent < self.current.info.outer:
            self._push_value()
            self.info_state = DuckParser.INFO_STATE_NONE
            self._parse_line(line)
            return
        iline = line[indent:]
        if iline.startswith('@'):
            self._parse_line_info_info(iline, indent)
        else:
            # Block content at the same (or less) indent level as the
            # info elements doesn't belong to info. It starts the body.
            if indent <= self.current.info.outer:
                self._push_value()
                self.info_state = DuckParser.INFO_STATE_NONE
                self._parse_line(line)
                return
            self._parse_line_info_block(iline, indent)

    def _parse_line_info_info(self, iline, indent):
        # Unlike block elements, info elements are never children of
        # preceding info elements at the same indent level. Unravel
        # as long as the current info's outer indent is the same.
        if indent <= self.curinfo.outer:
            self._push_value()
            while indent <= self.curinfo.outer:
                if self.curinfo == self.current.info:
                    break
                self.curinfo = self.curinfo.parent
        # First line after an @info declaration? Set inner indent.
        if self.info_state == DuckParser.INFO_STATE_READY:
            self.curinfo.inner = indent
        self.info_state = DuckParser.INFO_STATE_INFO

        for j in range(1, len(iline)):
            if not _isnmtoken(iline[j]):
                break
        name = iline[1:j]
        node = Info(name, indent)
        self.curinfo.add_child(node)
        self.curinfo = node

        if iline[j] == '[':
            self.info_state = DuckParser.INFO_STATE_ATTR
            self._attrparser = AttributeParser(self)
            self._parse_line_info_attr(iline[j + 1:])
        else:
            self._value = iline[j:].lstrip()
            if self._value == '':
                self.info_state = DuckParser.INFO_STATE_READY

    def _parse_line_info_block(self, iline, indent):
        # If we're already inside a leaf element, we only break out
        # if the indent is less than the inner indent. For example:
        # @p
        # Inside of p
        if self.curinfo.terminal:
            if indent < self.curinfo.inner:
                self._push_value()
                self.curinfo = self.curinfo.parent
        # If we're not in a leaf, we need to create an implicit
        # info paragraph, but only after breatking out to the
        # level of the outer indent. For example:
        # @foo
        # Not inside of foo, and in implicit p
        else:
            if indent <= self.curinfo.outer:
                self._push_value()
                while indent <= self.curinfo.outer:
                    if self.curinfo == self.current.info:
                        break
                    self.curinfo = self.curinfo.parent
            node = Info('p', indent)
            self.curinfo.add_child(node)
            self.curinfo = node

        # First line after an @info declaration? Set inner indent.
        if self.info_state == DuckParser.INFO_STATE_READY:
            self.curinfo.inner = indent
            self.info_state = DuckParser.INFO_STATE_BLOCK

        self.info_state = DuckParser.INFO_STATE_BLOCK

        self._value += iline

    def _parse_line_info_attr(self, line):
        self._attrparser.parse_line(line)
        if self._attrparser.finished:
            self.curinfo.attributes = self._attrparser.attributes
            self._value = self._attrparser.remainder.lstrip()
            self._attrparser = None
            if self._value == '':
                self.info_state = DuckParser.INFO_STATE_READY
            else:
                self.info_state = DuckParser.INFO_STATE_INFO

    def _parse_line_block(self, line):
        # Blank lines close off elements that have inline content (terminal)
        # unless they're verbatim elements that have an inner indent. Only
        # decreasing indent can break free of those. They also break out of
        # unindented block container elements, except for a set of special
        # elements that take lists of things instead of general blocks.
        if line.strip() == '':
            if self.current.terminal:
                if (self.current.verbatim and
                    self.current.inner > self.current.outer):
                    self._value += '\n'
                else:
                    self._push_value()
                    self.current = self.current.parent
            while self.current.inner == self.current.outer:
                if self.current.division:
                    break
                if self.current.name in ('list', 'steps', 'terms', 'tree'):
                    break
                if self.current.name in ('table', 'thead', 'tfoot', 'tbody', 'tr'):
                    break
                if self.current.terminal:
                    self._push_value()
                self.current = self.current.parent
            return

        sectd = 0
        if line.startswith('=='):
            i = 0
            while i < len(line) and line[i] == '=':
                i += 1
            if i < len(line) and line[i] == ' ':
                sectd = i
        if sectd > 0:
            self._push_value()
            while not self.current.division:
                self.current = self.current.parent
            while self.current.depth >= sectd:
                self.current = self.current.parent
            if sectd != self.current.depth + 1:
                raise SyntaxError('Incorrect section depth', self)
            section = Block('section', linenum=self.linenum)
            self.current.add_child(section)
            title = Block('title', 0, sectd + 1, linenum=self.linenum)
            section.add_child(title)
            self.current = title
            self._value = line[sectd + 1:]
            self.state = DuckParser.STATE_HEADER
            return

        # If the indent is less than what we can append to the current
        # node, unravel until we're at the same indent level. Note that
        # this still might not be the right level. We may or may not be
        # able to add children to a block at the same indent, but we'll
        # handle that later, because it depends on stuff.
        indent = self._get_indent(line)
        if indent < self.current.inner:
            self._push_value()
            while (not self.current.division) and self.current.inner > indent:
                self.current = self.current.parent

        if self.current.verbatim:
            iline = line[self.current.inner:]
        else:
            iline = line[indent:]
        if iline.startswith('['):
            # Start a block with a standard block declaration.
            self._push_value()
            while (not self.current.division and (
                    self.current.terminal or
                    self.current.outer > indent)):
                self.current = self.current.parent

            for j in range(1, len(iline)):
                if not _isnmtoken(iline[j]):
                    break
            name = iline[1:j]

            # Now we unravel a bit more. We do not want current to be
            # at the same indent level, unless one of a number of special
            # case conditions is met.
            while (not self.current.division and (
                    not self.current.available and
                    self.current.outer == indent)):
                if name == 'item' and self.current.list:
                    break
                if name in ('td', 'th') and self.current.name == 'tr':
                    break
                if (name == 'tr' and
                    self.current.name in ('table', 'thead', 'tfoot', 'tbody')):
                    break
                if (name in ('thead', 'tfoot', 'tbody') and
                    self.current.name == 'table'):
                    break
                self.current = self.current.parent

            node = Block(name, indent, linenum=self.linenum)
            self.current.add_child(node)
            self.current = node

            if iline[j] == ']':
                self.state = DuckParser.STATE_BLOCK_READY
            else:
                self._attrparser = AttributeParser(self)
                self._attrparser.parse_line(iline[j:])
                if self._attrparser.finished:
                    self.current.attributes = self._attrparser.attributes
                    self.state = DuckParser.STATE_BLOCK_READY
                    self._attrparser = None
                else:
                    self.state = DuckParser.STATE_BLOCK_ATTR
        elif iline.startswith('. '):
            self._parse_line_block_title(iline, indent)
        elif iline.startswith('- '):
            self._parse_line_block_item_title(iline, indent)
        elif iline.startswith('* '):
            self._parse_line_block_item_content(iline, indent)
        elif not self.current.terminal:
            while (not self.current.division and (
                    not self.current.available and
                    self.current.outer == indent)):
                self.current = self.current.parent
            node = Block('p', indent, linenum=self.linenum)
            self.current.add_child(node)
            self.current = node
            self._value += iline
        else:
            self._value += iline

    def _parse_line_block_title(self, iline, indent):
        self._push_value()
        while ((not self.current.division) and
               (self.current.terminal or self.current.outer > indent)):
            self.current = self.current.parent
        title = Block('title', indent, indent + 2, linenum=self.linenum)
        self.current.add_child(title)
        self.current = title
        self._parse_line((' ' * self.current.inner) + iline[2:])

    def _parse_line_block_item_title(self, iline, indent):
        self._push_value()
        while ((not self.current.division) and
               (self.current.terminal or self.current.outer > indent)):
            self.current = self.current.parent

        if self.current.name == 'tr':
            node = Block('th', indent, indent + 2, linenum=self.linenum)
            self.current.add_child(node)
            self.current = node
            self._parse_line((' ' * node.inner) + iline[2:])
            return

        if self.current.name != 'terms':
            node = Block('terms', indent, linenum=self.linenum)
            self.current.add_child(node)
            self.current = node
        # By now we've unwound to the terms element. If the preceding
        # block was a title, then the last item will have only title
        # elements, and we just keep appending there.
        if (not self.current.empty
            and isinstance(self.current.children[-1], Block)
            and self.current.children[-1].name == 'item'):
            item = self.current.children[-1]
            if (not item.empty
                and isinstance(self.current.children[-1], Block)
                and item.children[-1].name == 'title'):
                self.current = item
        if self.current.name != 'item':
            item = Block('item', indent, indent + 2, linenum=self.linenum)
            self.current.add_child(item)
            self.current = item
        title = Block('title', indent, indent + 2, linenum=self.linenum)
        self.current.add_child(title)
        self.current = title
        self._parse_line((' ' * self.current.inner) + iline[2:])

    def _parse_line_block_item_content(self, iline, indent):
        self._push_value()
        while ((not self.current.division) and
               (self.current.terminal or self.current.outer > indent)):
            self.current = self.current.parent

        if self.current.name == 'tr':
            node = Block('td', indent, indent + 2, linenum=self.linenum)
            self.current.add_child(node)
            self.current = node
            self._parse_line((' ' * node.inner) + iline[2:])
        elif self.current.name == 'terms':
            # All the logic above will have unraveled us from the item
            # created by the title, so we have to step back into it.
            if self.current.empty or self.current.children[-1].name != 'item':
                raise SyntaxError('Missing item title in terms', self)
            self.current = self.current.children[-1]
            self._parse_line((' ' * self.current.inner) + iline[2:])
        elif self.current.name == 'tree':
            FIXME(self.current.name)
        elif self.current.name in ('list', 'steps'):
            item = Block('item', indent, indent + 2, linenum=self.linenum)
            self.current.add_child(item)
            self.current = item
            self._parse_line((' ' * item.inner) + iline[2:])
        else:
            node = Block('list', indent, linenum=self.linenum)
            self.current.add_child(node)
            item = Block('item', indent, indent + 2, linenum=self.linenum)
            node.add_child(item)
            self.current = item
            self._parse_line((' ' * item.inner) + iline[2:])

    def _parse_line_block_attr(self, line):
        self._attrparser.parse_line(line)
        if self._attrparser.finished:
            self.current.attributes = self._attrparser.attributes
            self.state = DuckParser.STATE_BLOCK_READY
            self._attrparser = None

    def _parse_line_block_ready(self, line):
        indent = self._get_indent(line)
        if indent < self.current.outer:
            while ((not self.current.division) and
                   (self.current.outer > indent)):
                self.current = self.current.parent
        else:
            if line.lstrip().startswith('@'):
                self.info_state = DuckParser.INFO_STATE_INFO
            self.current.inner = self._get_indent(line)
        self.state = DuckParser.STATE_BLOCK
        self._parse_line(line)

    def _get_indent(self, line):
        for i in range(len(line)):
            if line[i] != ' ':
                return i

    def _push_value(self):
        if self._value != '':
            if self.info_state != DuckParser.INFO_STATE_NONE:
                self.curinfo.add_text(self._value)
            else:
                self.current.add_text(self._value)
            self._value = ''


def _isnmtoken(c):
    i = ord(c)
    return (('A' <= c <= 'Z') or ('a' <= c <= 'z') or ('0' <= c <= '9') or
            (c == ':' or c == '_' or c == '-' or c == '.' or i == 0xB7) or
            (0xC0 <= i <= 0xD6) or (0xD8 <= i <= 0xF6) or
            (0xF8 <= i <= 0x2FF) or (0x370 <= i <= 0x37D) or
            (0x37F <= i <= 0x1FFF) or (0x200C <= i <= 0x200D) or
            (0x2070 <= i <= 0x218F) or (0x2C00 <= i <= 0x2FEF) or
            (0x3001 <= i <= 0xD7FF) or (0xF900 <= i <= 0xFDCF) or
            (0xFDF0 <= i <= 0xFFFD) or (0x10000 <= i <= 0xEFFFF) or
            (0x0300 <= i <= 0x036F) or (0x203F <= i <= 0x2040))
