# Copyright (c) 2014-2019 Shaun McCance <shaunm@gnome.org>
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

import collections
import importlib
import inspect
import os
import sys
import urllib.parse

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

_escaped_chars = '$*=-.@[]()"\''


class Attributes:
    def __init__(self):
        self._attrlist = []
        self._attrvals = {}

    def add_attribute(self, key, value):
        if key not in self._attrlist:
            self._attrlist.append(key)
        if key in ('style', 'type'):
            self._attrvals.setdefault(key, [])
            self._attrvals[key].append(value)
        else:
            self._attrvals[key] = value

    def get_attribute(self, key):
        val = self._attrvals.get(key)
        if isinstance(val, list):
            return ' '.join(val)
        else:
            return val

    def get_attributes(self):
        return self._attrlist

    def __contains__(self, item):
        return item in self._attrlist

    def _write_xml(self, fd):
        for attr in self._attrlist:
            fd.write(' ' + attr + '="')
            val = self._attrvals[attr]
            if isinstance(val, list):
                fd.write(' '.join([_escape_xml_attr(s) for s in val]))
            else:
                fd.write(_escape_xml_attr(val))
            fd.write('"')


class Directive:
    def __init__(self, name):
        self.name = name
        self.content = ''

    def set_content(self, content):
        self.content = content

    @staticmethod
    def parse_line(line, parser):
        i = 1
        while i < len(line):
            if line[i].isspace():
                break
            i += 1
        if i == 1:
            raise SyntaxError('Directive must start with a name', parser)
        directive = Directive(line[1:i])
        directive.set_content(line[i:].lstrip().rstrip('\n'))
        return directive


class Node:
    def __init__(self, name, outer=0, inner=None, parser=None, linenum=None, extensions=False):
        self.name = name
        self.nsprefix = None
        self.nsuri = None
        self.localname = name
        self.default_namespace = None
        self.extension = None
        self.is_external = False
        if ':' in name:
            self.nsprefix = name[:name.index(':')]
            self.nsuri = parser.document.get_namespace(self.nsprefix)
            self.localname = self.name[len(self.nsprefix)+1:]
            if self.nsuri is not None and not self.nsuri.startswith('http://projectmallard.org/'):
                self.is_external = True
            if extensions and parser is not None:
                if self.nsprefix in parser.extensions_by_module:
                    self.extension = self.nsprefix
            if self.extension is None:
                if self.nsuri is None:
                    if self.nsprefix == 'xml':
                        pass
                    elif self.nsprefix == 'its':
                        parser.document.add_namespace('its', 'http://www.w3.org/2005/11/its')
                    else:
                        raise SyntaxError('Unrecognized namespace prefix: ' + self.nsprefix,
                                          parser)
        else:
            self.localname = name
        self.outer = outer
        if inner is None:
            self.inner = outer
        else:
            self.inner = inner
        self.info = None
        self.children = []
        self.attributes = None
        self.is_verbatim = (name in ('screen', 'code'))
        self.is_list = (name in ('list', 'steps', 'terms', 'tree'))
        self.is_greedy = self.is_name((
            'list', 'steps', 'terms', 'tree',
            'table', 'thead', 'tfoot', 'tbody', 'tr'))
        self._is_leaf = None
        self.linenum = linenum
        if self.linenum is None and parser is not None:
            self.linenum = parser.linenum
        self._namespaces = collections.OrderedDict()
        self._definitions = {}
        self._parent = None
        self._softbreak = False # Help keep out pesky trailing newlines

    def is_name(self, localname, nsuri=None):
        if nsuri in (None, 'http://projectmallard.org/1.0/'):
            if self.nsuri not in (None, 'http://projectmallard.org/1.0/'):
                return False
        else:
            if nsuri != self.nsuri:
                return False

        if isinstance(localname, (list, tuple)):
            for name in localname:
                if name == self.localname:
                    return True
            return False
        else:
            return localname == self.localname

    @property
    def is_leaf(self):
        if self._is_leaf is not None:
            return self._is_leaf
        leafs = ('p', 'screen', 'code', 'title', 'subtitle', 'desc', 'cite', 'name', 'email', 'years')
        if self.is_name(leafs):
            return True
        if self.nsprefix is not None:
            if self.nsuri is None:
                return False
            if self.nsuri == 'http://projectmallard.org/1.0/':
                return self.localname in leafs
        return False

    @is_leaf.setter
    def is_leaf(self, is_leaf):
        self._is_leaf = is_leaf

    @property
    def is_tree_item(self):
        if not self.is_name('item'):
            return False
        cur = self
        while cur.is_name('item'):
            cur = cur.parent
        if cur.is_name('tree'):
            return True
        return False

    @property
    def has_tree_items(self):
        if self.is_tree_item:
            for item in self.children:
                if isinstance(item, Node) and item.is_name('item'):
                    return True
        return False

    @property
    def is_external_leaf(self):
        if not self.is_external:
            return False
        if len(self.children) == 0:
            return False
        if isinstance(self.children[0], str) or isinstance(self.children[0], Inline):
            return True
        return False

    @property
    def is_empty(self):
        return len(self.children) == 0 and self.info is None

    @property
    def available(self):
        for child in self.children:
            if not child.is_name(('title', 'desc', 'cite')):
                return False
        return True

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, node):
        self._parent = node

    def add_child(self, child):
        if isinstance(child, str):
            self.add_text(child)
            return
        if self._softbreak:
            if len(self.children) > 0:
                self.children[-1] += '\n'
            self._softbreak = False
        self.children.append(child)
        child.parent = self

    def insert_child(self, index, child):
        self.children.insert(index, child)
        child.parent = self

    def add_text(self, text):
        # We don't add newlines when we see them. Instead, we record that
        # we saw one with _softbreak and output the newline if we add
        # something afterwards. This prevents pesky trailing newlines on
        # text in block elements. But we only do newline mangling at the
        # block parse phase, so don't bother if self is an Inline.
        if self._softbreak:
            if len(self.children) > 0:
                self.children[-1] += '\n'
            self._softbreak = False
        if not isinstance(self, Inline) and text.endswith('\n'):
            text = text[:-1]
            self._softbreak = True
        if len(self.children) > 0 and isinstance(self.children[-1], str):
            self.children[-1] += text
        else:
            self.children.append(text)

    def add_namespace(self, prefix, uri):
        self._namespaces[prefix] =uri

    def get_namespace(self, prefix):
        uri = self._namespaces.get(prefix)
        if uri is not None:
            return uri
        if self._parent is not None:
            return self._parent.get_namespace(prefix)
        return None

    def add_definition(self, name, value):
        self._definitions[name] = value

    def write_xml(self, outfile=None):
        close = False
        if outfile is None:
            fd = sys.stdout
        elif isinstance(outfile, str):
            close = True
            fd = open(outfile, 'w', encoding='utf-8')
        else:
            fd = outfile
        self._write_xml(fd)
        if close:
            fd.close()

    def _write_xml(self, fd, *, depth=0, verbatim=False):
        verbatim = verbatim or self.is_verbatim
        if not isinstance(self, Inline):
            fd.write(' ' * depth)
        fd.write('<' + self.name)
        if self.default_namespace is not None:
            fd.write(' xmlns="' + self.default_namespace + '"')
        for prefix in self._namespaces:
            fd.write(' xmlns:' + prefix + '="' + self._namespaces[prefix] + '"')
        if self.attributes is not None:
            self.attributes._write_xml(fd)
        if self.is_empty:
            if isinstance(self, Inline):
                fd.write('/>')
            else:
                fd.write('/>\n')
        elif (isinstance(self.children[0], Block) or
              isinstance(self.children[0], Info) ):
            fd.write('>\n')
        else:
            fd.write('>')

        for i in range(len(self.children)):
            child = self.children[i]
            if isinstance(child, Inline):
                child._write_xml(fd, depth=depth, verbatim=verbatim)
            elif isinstance(child, Fence):
                child._write_xml(fd, depth=depth, verbatim=verbatim)
                if i + 1 < len(self.children):
                    fd.write('\n')
            elif isinstance(child, Node):
                child._write_xml(fd, depth=depth+1, verbatim=verbatim)
            else:
                if i > 0 and isinstance(self.children[i-1], Fence) and not verbatim:
                    fd.write(' ' * depth)
                if '\n' in child:
                    nl = child.find('\n')
                    while nl >= 0:
                        if nl + 1 == len(child) and i + 1 == len(self.children):
                            fd.write(_escape_xml(child[:nl]))
                        elif verbatim or (nl + 1 < len(child) and child[nl + 1] == '\n'):
                            fd.write(_escape_xml(child[:nl]) + '\n')
                        elif self.is_tree_item:
                            fd.write(_escape_xml(child[:nl]) + '\n')
                            if nl + 1 < len(child):
                                fd.write(' ' * (depth + 1))
                        else:
                            fd.write(_escape_xml(child[:nl]) + '\n' + (' ' * depth))
                        child = child[nl + 1:]
                        nl = child.find('\n')
                    if child != '':
                        fd.write(_escape_xml(child))
                else:
                    fd.write(_escape_xml(child))
        if not self.is_empty:
            leafy = self.is_leaf or self.is_external_leaf
            for child in self.children:
                if isinstance(child, (Block, Info)):
                    leafy = False
                    break
            if isinstance(self, Inline):
                fd.write('</' + self.name + '>')
            elif leafy:
                fd.write('</' + self.name + '>\n')
            elif self.is_tree_item:
                if self.has_tree_items:
                    fd.write((' ' * depth) + '</' + self.name + '>\n')
                else:
                    fd.write('</' + self.name + '>\n')
            else:
                fd.write((' ' * depth) + '</' + self.name + '>\n')


class Document(Node):
    def __init__(self, parser=None):
        Node.__init__(self, '_', parser=parser)
        self.divdepth = 0
        self.default_namespace = 'http://projectmallard.org/1.0/'

    def _write_xml(self, fd, *args, depth=0, verbatim=False):
        if len(self.children) == 1:
            fd.write('<?xml version="1.0" encoding="utf-8"?>\n')
        for child in self.children:
            if child.default_namespace is None:
                child.default_namespace = self.default_namespace
            for ns in self._namespaces:
                child.add_namespace(ns, self._namespaces[ns])
            child._write_xml(fd)


class Division(Node):
    def __init__(self, name, depth, **kwargs):
        Node.__init__(self, name, **kwargs)
        self.divdepth = depth


class Block(Node):
    pass


class Info(Node):
    pass


class Inline(Node):
    pass


class Fence(Node):
    def add_line(self, line):
        self.add_text(line)
        return
        indent = DuckParser.get_indent(line)
        if len(self.children) == 0:
            self.inner = indent
            self.children.append('')
        self.children[0] += line[min(indent, self.inner):]
        if not line.endswith('\n'):
            self.children[0] += '\n'

    def _write_xml(self, fd, *, depth=0, verbatim=False):
        lines = self.children[0].split('\n')
        trim = min(self.inner, DuckParser.get_indent(lines[0]))
        for i in range(len(lines)):
            line = lines[i]
            indent = DuckParser.get_indent(line)
            if i != 0:
                fd.write('\n')
            fd.write(_escape_xml(line[min(indent, trim):]))


class NodeFactory:
    def __init__(self, parser):
        self.parser = parser
        self.id_attribute = 'id'

    def create_info_node(self, name, outer):
        node = Info(name, outer=outer, parser=self.parser, extensions=True)
        return node

    def create_info_paragraph_node(self, outer):
        node = Info('p', outer=outer, parser=self.parser)
        return node

    def create_block_node(self, name, outer):
        node = Block(name, outer=outer, parser=self.parser, extensions=True)
        return node

    def create_block_paragraph_node(self, outer):
        node = Block('p', outer=outer, parser=self.parser)
        return node

    def handle_division_title(self, depth, inner):
        name = 'page' if (depth == 1) else 'section'
        page = Division(name, depth=depth, parser=self.parser)
        title = Block('title', inner=inner, parser=self.parser)
        self.parser.current.add_child(page)
        page.add_child(title)
        self.parser.current = title

    def handle_division_subtitle(self, depth, inner):
        node = Block('subtitle', inner=inner, parser=self.parser)
        self.parser.current.add_child(node)
        self.parser.current = node

    def handle_info_container(self, outer):
        info = Block('info', outer=outer, parser=self.parser)
        self.parser.current.insert_child(0, info)
        self.parser.current.info = info
        info.parent = self.parser.current

    def handle_block_title(self, outer, inner):
        # For lines starting with '. '. Creates a block title.
        title = Block('title', outer,  inner, parser=self.parser)
        self.parser.current.add_child(title)
        self.parser.current = title

    def handle_block_item_title(self, outer, inner):
        # For lines starting with '- '. It might be a th element,
        # or it might be a title in a terms item. It might also
        # start a terms element.
        if self.parser.current.is_name('tr'):
            node = Block('th', outer, inner, parser=self.parser)
            self.parser.current.add_child(node)
            self.parser.current = node
            return

        if not self.parser.current.is_name('terms'):
            node = Block('terms', outer, parser=self.parser)
            self.parser.current.add_child(node)
            self.parser.current = node
        # By now we've unwound to the terms element. If the preceding
        # block was a title, then the last item will have only title
        # elements, and we just keep appending there.
        if (not self.parser.current.is_empty
            and isinstance(self.parser.current.children[-1], Block)
            and self.parser.current.children[-1].is_name('item')):
            item = self.parser.current.children[-1]
            if (not item.is_empty
                and isinstance(self.parser.current.children[-1], Block)
                and item.children[-1].is_name('title')):
                self.parser.current = item
        if not self.parser.current.is_name('item'):
            item = Block('item', outer, inner, parser=self.parser)
            self.parser.current.add_child(item)
            self.parser.current = item
        title = Block('title', outer, inner, parser=self.parser)
        self.parser.current.add_child(title)
        self.parser.current = title

    def handle_block_item_content(self, outer, inner):
        # For lines starting with '* '. It might be a td element,
        # it might be an item element in a list or steps, it might
        # be a tree item, or it might start the content of an item
        # in a terms. It might also start a list element.
        if self.parser.current.is_name('tr'):
            node = Block('td', outer=outer, inner=inner, parser=self.parser)
            self.parser.current.add_child(node)
            self.parser.current = node
            return node
        elif self.parser.current.is_name('terms'):
            # All the logic above will have unraveled us from the item
            # created by the title, so we have to step back into it.
            if self.parser.current.is_empty or not self.parser.current.children[-1].is_name('item'):
                raise SyntaxError('Missing item title in terms', self.parser)
            self.parser.current = self.parser.current.children[-1]
            return self.parser.current
        elif self.parser.current.is_name('tree') or self.parser.current.is_tree_item:
            item = Block('item', outer=outer, inner=inner, parser=self.parser)
            self.parser.current.add_child(item)
            self.parser.current = item
            return item
        elif self.parser.current.is_name(('list', 'steps')):
            item = Block('item', outer=outer, inner=inner, parser=self.parser)
            self.parser.current.add_child(item)
            self.parser.current = item
            return item
        else:
            node = Block('list', outer=outer, parser=self.parser)
            self.parser.current.add_child(node)
            item = Block('item', outer=outer, inner=inner, parser=self.parser)
            node.add_child(item)
            self.parser.current = item
            return item


class SyntaxError(Exception):
    def __init__(self, message, parser):
        self.message = message
        self.parser = parser
        self.filename = parser.filename if parser else None
        self.linenum = parser.linenum if parser else None
        self.fullmessage = ''
        if self.filename is not None:
            self.fullmessage += os.path.basename(self.filename)
            if self.linenum is not None:
                self.fullmessage += ':' + str(self.linenum)
            self.fullmessage += ': '
        self.fullmessage += self.message


class ParserExtension:
    def __init__(self, parser, prefix, version):
        pass

    def parse_line_block(self, line):
        return False

    def take_directive(self, directive):
        return False

    def take_block_node(self, node):
        return False


class InlineParser:
    def __init__(self, parent, linenum=1):
        # Dummy node just to hold children while we parse
        self.current = Inline('_', linenum=linenum)
        self.document = parent.document
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
        parens = []
        while cur < len(text):
            if self.current.parent is not None and text[cur] == ')':
                if len(parens) > 0 and parens[-1] > 0:
                    parens[-1] -= 1
                    cur += 1
                else:
                    self.current.add_text(text[start:cur])
                    self.current = self.current.parent
                    parens.pop()
                    cur += 1
                    start = cur
            elif self.current.parent is not None and text[cur] == '(':
                parens[-1] += 1
                cur += 1
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
                        parser = InlineParser(self,
                                              linenum=self.current.linenum)
                        for child in parser.parse_text(entval):
                            if isinstance(child, str):
                                self.current.add_text(child)
                            else:
                                self.current.add_child(child)
                    else:
                        raise SyntaxError('Unrecognized entity: ' + entname, self)
                    start = cur = end + 1
                elif text[end] == '[':
                    self.current.add_text(text[start:cur])
                    node = Inline(text[cur + 1:end], parser=self)
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
                        parens.append(0)
                        start = cur = cur + 1
                elif text[end] == '(':
                    self.current.add_text(text[start:cur])
                    node = Inline(text[cur + 1:end], parser=self)
                    self.current.add_child(node)
                    self.current = node
                    parens.append(0)
                    start = cur = end + 1
                else:
                    cur = end
            else:
                if text[cur] == '\n':
                    self.linenum += 1
                cur += 1


class AttributeParser:
    def __init__(self, parent, node=None):
        self.remainder = ''
        self.node = node
        self.attributes = Attributes()
        self.finished = False
        self.filename = parent.filename
        self.linenum = parent.linenum
        self._quote = None
        self._value = ''
        self._attrname = None
        self._parent = parent

    def lookup_entity(self, entity):
        return self._parent.lookup_entity(entity)

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
                        entval = self.lookup_entity(entname)
                        if entval is not None:
                            parser = AttributeParser(self)
                            retval += parser.parse_value(entval)
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
                if self._quote is not None:
                    self._value += line[i:j]
                i = j + 1
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
                    if len(line) > i + 1 and line[i + 1] == '>':
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
                    if ':' in word:
                        nsprefix, localname = word.split(':', maxsplit=1)
                        nsuri = self._parent.document.get_namespace(nsprefix)
                        if nsuri is None:
                            if nsprefix == 'xml':
                                pass
                            elif nsprefix == 'its':
                                self._parent.document.add_namespace('its', 'http://www.w3.org/2005/11/its')
                            else:
                                raise SyntaxError('Unrecognized namespace prefix: ' + nsprefix,
                                                  self)
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
                    raise SyntaxError('Invalid character ' + line[j] +
                                      ' in attribute list', self)


class DirectiveIncludeParser:
    def __init__(self, parent):
        self.parent = parent
        self.document = parent.document
        self.extensions = []
        self.extensions_by_module = {}
        self._start = True
        self._comment = False

    def parse_file(self, filename):
        self.filename = filename
        self.absfilename = os.path.join(os.path.dirname(self.parent.absfilename),
                                        filename)
        if isinstance(self.parent, DuckParser):
            self._parentfiles = [self.parent.absfilename, self.absfilename]
        else:
            self._parentfiles = self.parent._parentfiles + [self.absfilename]
        self.linenum = 0
        try:
            fd = open(self.absfilename, encoding='utf-8')
        except:
            raise SyntaxError('Missing included file ' + filename, self.parent)
        for line in fd:
            self.parse_line(line)
        fd.close()

    def parse_line(self, line):
        self.linenum += 1

        if self._comment:
            if line.strip() == '--]':
                self._comment = False
            return
        indent = DuckParser.get_indent(line)
        iline = line[indent:]
        if iline.startswith('[-]'):
            return
        elif iline.startswith('[--'):
            self._comment = True
            return

        if line.strip() == '':
            return
        if not(line.startswith('@')):
            raise SyntaxError('Directive includes can only include directives', self)
        self._parse_line(line)

    def take_directive(self, directive):
        if directive.name.startswith('ducktype/'):
            if not self._start:
                raise SyntaxError('Ducktype declaration must be first', self)
            if directive.name != 'ducktype/1.0':
                raise SyntaxError(
                    'Unsupported ducktype version: ' + directive.name ,
                    self)
            for value in directive.content.split():
                try:
                    prefix, version = value.split('/', maxsplit=1)
                    extmod = importlib.import_module('mallard.ducktype.extensions.' + prefix)
                    for extclsname, extcls in inspect.getmembers(extmod, inspect.isclass):
                        if issubclass(extcls, ParserExtension):
                            extension = extcls(self, prefix, version)
                            self.extensions.append(extension)
                            self.extensions_by_module.setdefault(prefix, [])
                            self.extensions_by_module[prefix].append(extension)
                except SyntaxError as e:
                    raise e
                except:
                    raise SyntaxError(
                        'Unsupported ducktype extension: ' + value,
                        self)
        elif ':' in directive.name:
            prefix, name = directive.name.split(':', maxsplit=1)
            if prefix not in self.extensions_by_module:
                raise SyntaxError('Unrecognized directive prefix: ' + prefix, self)
            for extension in self.extensions_by_module[prefix]:
                if extension.take_directive(directive):
                    return
            raise SyntaxError('Unrecognized directive: ' + directive.name, self)
        elif directive.name == 'define':
            try:
                self.parent.take_directive(directive)
            except SyntaxError as e:
                raise SyntaxError(e.message, self)
        elif directive.name == 'encoding':
            FIXME('encoding')
        elif directive.name == 'include':
            if ' ' in directive.content:
                raise SyntaxError('Multiple values in include. URL encode file name?', self)
            relfile = urllib.parse.unquote(directive.content)
            absfile = os.path.join(os.path.dirname(self.absfilename), relfile)
            if absfile in self._parentfiles:
                raise SyntaxError('Recursive include detected: ' + directive.content, self)
            incparser = DirectiveIncludeParser(self)
            incparser.parse_file(relfile)
        elif directive.name == 'namespace':
            try:
                self.parent.take_directive(directive)
            except SyntaxError as e:
                raise SyntaxError(e.message, self)
        else:
            raise SyntaxError('Unrecognized directive: ' + directive.name, self)
        self._start = False

    def _parse_line(self, line):
        directive = Directive.parse_line(line, self)
        self.take_directive(directive)


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
        self.linenum = 0
        self.document = Document(parser=self)
        self.current = self.document
        self.curinfo = None
        self.extensions = []
        self.extensions_by_module = {}
        self.factory = NodeFactory(self)

        self._text = ''
        self._attrparser = None
        self._defaultid = None
        self._comment = False
        self._fenced = False
        self._fragments = False

    @staticmethod
    def get_indent(line):
        for i in range(len(line)):
            if line[i] != ' ':
                return i
        return 0

    def lookup_entity(self, entity):
        cur = self.current
        while cur is not None:
            if entity in cur._definitions:
                return cur._definitions[entity]
            cur = cur.parent
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
        self.absfilename = os.path.abspath(filename)
        self._defaultid = os.path.basename(filename)
        if self._defaultid.endswith('.duck'):
            self._defaultid = self._defaultid[:-5]
        fd = open(filename, encoding='utf-8')
        for line in fd:
            self.parse_line(line)
        fd.close()

    def parse_inline(self, node=None):
        if node is None:
            node = self.document
        oldchildren = node.children
        node.children = []
        if node.info is not None:
            self.parse_inline(node.info)
        for child in oldchildren:
            if isinstance(child, str):
                parser = InlineParser(self, linenum=node.linenum)
                for c in parser.parse_text(child):
                    node.add_child(c)
            elif isinstance(child, Fence):
                node.add_child(child)
            else:
                self.parse_inline(child)
                node.add_child(child)

    def take_directive(self, directive):
        if directive.name.startswith('ducktype/'):
            if self.state != DuckParser.STATE_START:
                raise SyntaxError('Ducktype declaration must be first', self)
            if directive.name != 'ducktype/1.0':
                raise SyntaxError(
                    'Unsupported ducktype version: ' + directive.name ,
                    self)
            for value in directive.content.split():
                if value == '__future__/fragments':
                    self._fragments = True
                    continue
                try:
                    prefix, version = value.split('/', maxsplit=1)
                    extmod = importlib.import_module('mallard.ducktype.extensions.' + prefix)
                    for extclsname, extcls in inspect.getmembers(extmod, inspect.isclass):
                        if issubclass(extcls, ParserExtension):
                            extension = extcls(self, prefix, version)
                            self.extensions.append(extension)
                            self.extensions_by_module.setdefault(prefix, [])
                            self.extensions_by_module[prefix].append(extension)
                except SyntaxError as e:
                    raise e
                except:
                    raise SyntaxError(
                        'Unsupported ducktype extension: ' + value,
                        self)
        elif ':' in directive.name:
            prefix, name = directive.name.split(':', maxsplit=1)
            if prefix not in self.extensions_by_module:
                raise SyntaxError('Unrecognized directive prefix: ' + prefix, self)
            for extension in self.extensions_by_module[prefix]:
                if extension.take_directive(directive):
                    return
            raise SyntaxError('Unrecognized directive: ' + directive.name, self)
        elif directive.name == 'define':
            values = directive.content.split(maxsplit=1)
            if len(values) != 2:
                raise SyntaxError(
                    'Entity definition takes exactly two values',
                    self)
            self.current.add_definition(*values)
        elif directive.name == 'encoding':
            FIXME('encoding')
        elif directive.name == 'include':
            if ' ' in directive.content:
                raise SyntaxError('Multiple values in include. URL encode file name?', self)
            relfile = urllib.parse.unquote(directive.content)
            incparser = DirectiveIncludeParser(self)
            incparser.parse_file(relfile)
        elif directive.name == 'namespace':
            values = directive.content.split(maxsplit=1)
            if len(values) != 2:
                raise SyntaxError(
                    'Namespace declaration takes exactly two values',
                    self)
            if values[0] == 'xml':
                if values[1] != 'http://www.w3.org/XML/1998/namespace':
                    raise SyntaxError('Wrong value of xml namespace prefix', self)
            if values[0] == 'its':
                if values[1] != 'http://www.w3.org/2005/11/its':
                    raise SyntaxError('Wrong value of its namespace prefix', self)
            self.current.add_namespace(*values)
        else:
            raise SyntaxError('Unrecognized directive: ' + directive.name, self)

    def finish(self):
        if (self.state in (DuckParser.STATE_HEADER_ATTR, DuckParser.STATE_BLOCK_ATTR) or
            self.info_state == DuckParser.INFO_STATE_ATTR):
            raise SyntaxError('Unterminated block declaration', self)
        self.push_text()
        if self._defaultid is not None and len(self.document.children) == 1:
            root = self.document.children[0]
            if isinstance(root, Division):
                if root.attributes is None:
                    root.attributes = Attributes()
                idattr = self.factory.id_attribute
                if idattr not in root.attributes:
                    root.attributes.add_attribute(idattr, self._defaultid)
        self.parse_inline()

    def parse_line(self, line):
        self.linenum += 1
        self._parse_line(line)

    def _parse_line(self, line):
        # If we're inside a comment or a no-parse fence, nothing else matters.
        if self._comment:
            if line.strip() == '--]':
                self._comment = False
            return
        if self._fenced:
            if line.strip() == ']]]':
                self._fenced = False
                self.current = self.current.parent
            else:
                self.current.add_line(line)
            return

        indent = DuckParser.get_indent(line)
        iline = line[indent:]

        if iline.startswith('[-]'):
            return
        elif iline.startswith('[--'):
            self._comment = True
            return
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
        elif self.state == DuckParser.STATE_HEADER_INFO:
            self._parse_line_header_info(line)
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
        elif line.startswith('@'):
            self._parse_line_directive(line)
        elif line.startswith('= '):
            self.factory.handle_division_title(depth=1, inner=2)
            self.set_text(line[2:])
            self.state = DuckParser.STATE_HEADER
        elif line.strip().startswith('[') or line.startswith('=='):
            if self._fragments == False:
                raise SyntaxError('Missing page header', self)
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)
        else:
            raise SyntaxError('Missing page header', self)

    def _parse_line_directive(self, line):
        directive = Directive.parse_line(line, self)
        self.take_directive(directive)
        if self.state == DuckParser.STATE_START:
            self.state == DuckParser.STATE_TOP

    def _parse_line_header(self, line):
        indent = DuckParser.get_indent(line)
        iline = line[indent:]
        if iline.startswith('@'):
            self.push_text()
            self.current = self.current.parent
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        elif indent > 0 and iline.startswith('['):
            self._parse_line_header_attr_start(line)
        elif indent >= self.current.inner:
            self.add_text(line[self.current.inner:])
        else:
            self.push_text()
            self.current = self.current.parent
            self.state = DuckParser.STATE_HEADER_POST
            self._parse_line(line)

    def _parse_line_header_post(self, line):
        depth = self.current.divdepth
        if line.startswith(('-' * depth) + ' '):
            self.factory.handle_division_subtitle(depth=depth, inner=depth+1)
            self.set_text(line[depth + 1:])
            self.state = DuckParser.STATE_SUBHEADER
        elif line.lstrip().startswith('@'):
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        elif line.strip() == '':
            self.state = DuckParser.STATE_HEADER_INFO
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_subheader(self, line):
        indent = DuckParser.get_indent(line)
        iline = line[indent:]
        if iline.startswith('@'):
            self.push_text()
            self.current = self.current.parent
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        elif indent > 0 and iline.startswith('['):
            self._parse_line_header_attr_start(line)
        elif indent >= self.current.inner:
            self.add_text(line[self.current.inner:])
        else:
            self.push_text()
            self.current = self.current.parent
            self.state = DuckParser.STATE_SUBHEADER_POST
            self._parse_line(line)

    def _parse_line_subheader_post(self, line):
        if line.lstrip().startswith('@'):
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        elif line.strip() == '':
            self.state = DuckParser.STATE_HEADER_INFO
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_header_attr_start(self, line):
        indent = DuckParser.get_indent(line)
        if indent > 0 and line[indent:].startswith('['):
            self.push_text()
            self.current = self.current.parent
            self._attrparser = AttributeParser(self)
            self._attrparser.parse_line(line[indent + 1:])
            if self._attrparser.finished:
                self.current.attributes = self._attrparser.attributes
                self.state = DuckParser.STATE_HEADER_ATTR_POST
                self._attrparser = None
            else:
                self.state = DuckParser.STATE_HEADER_ATTR
        else:
            self.push_text()
            self.current = self.current.parent
            self.state = DuckParser.STATE_HEADER_ATTR_POST
            self._parse_line(line)

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
        elif line.strip() == '':
            self.state = DuckParser.STATE_HEADER_INFO
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_header_info(self, line):
        if line.lstrip().startswith('@'):
            self.state = DuckParser.STATE_BLOCK
            self.info_state = DuckParser.INFO_STATE_INFO
            self._parse_line(line)
        elif line.strip() == '':
            self.state = DuckParser.STATE_HEADER_INFO
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_info(self, line):
        if line.strip() == '':
            # If the info elements weren't indented past the indent
            # level of the parent and the parent is a block, blank
            # line terminates info, because it must terminate the
            # block according to block processing rules.
            if (self.current.outer == self.current.inner and not isinstance(self.current, Division)):
                self.push_text()
                self.info_state = DuckParser.INFO_STATE_NONE
                self._parse_line(line)
                return
            # If we're inside a leaf element like a paragraph, break
            # out of that. Unless it's an indented verbatim element,
            # in which case the newline is just part of the content.
            if self.curinfo.is_leaf:
                if (self.curinfo.is_verbatim and
                    self.curinfo.inner > self.curinfo.outer):
                    self.add_text('\n')
                else:
                    self.push_text()
                    self.curinfo = self.curinfo.parent
                    self.info_state = DuckParser.INFO_STATE_INFO
            return

        indent = DuckParser.get_indent(line)
        if self.current.info is None:
            self.factory.handle_info_container(indent)
            self.curinfo = self.current.info
        if indent < self.current.info.outer:
            self.push_text()
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
                self.push_text()
                self.info_state = DuckParser.INFO_STATE_NONE
                self._parse_line(line)
                return
            self._parse_line_info_block(iline, indent)

    def _parse_line_info_info(self, iline, indent):
        # Unlike block elements, info elements are never children of
        # preceding info elements at the same indent level. Unravel
        # as long as the current info's outer indent is the same.
        if indent <= self.curinfo.outer:
            self.push_text()
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
        node = self.factory.create_info_node(name, indent)
        self.curinfo.add_child(node)
        self.curinfo = node

        if iline[j] == '[':
            self.info_state = DuckParser.INFO_STATE_ATTR
            self._attrparser = AttributeParser(self)
            self._parse_line_info_attr(iline[j + 1:])
        else:
            remainder = iline[j:].lstrip()
            if remainder != '':
                if not self.curinfo.is_leaf:
                    pnode = self.factory.create_info_paragraph_node(self.curinfo.outer)
                    self.curinfo.add_child(pnode)
                    self.curinfo = pnode
                self.set_text(remainder)
            else:
                self.info_state = DuckParser.INFO_STATE_READY

    def _parse_line_info_block(self, iline, indent):
        # If we're already inside a leaf element, we only break out
        # if the indent is less than the inner indent. For example:
        # @p
        # Inside of p
        if self.curinfo.is_leaf or self.curinfo.is_external:
            if indent < self.curinfo.inner:
                self.push_text()
                self.curinfo = self.curinfo.parent
        # If we're not in a leaf, we need to create an implicit
        # info paragraph, but only after breaking out to the
        # level of the outer indent. For example:
        # @foo
        # Not inside of foo, and in implicit p
        else:
            if indent <= self.curinfo.outer:
                self.push_text()
                while indent <= self.curinfo.outer:
                    if self.curinfo == self.current.info:
                        break
                    self.curinfo = self.curinfo.parent

        # After all that unraveling, if we're not in a leaf or external,
        # and only if we have real text to add, create an implicit p.
        if iline.strip() != '' and not (
                self.curinfo.is_leaf or self.curinfo.is_external):
            node = self.factory.create_info_paragraph_node(indent)
            self.curinfo.add_child(node)
            self.curinfo = node

        # First line after an @info declaration? Set inner indent.
        if self.info_state == DuckParser.INFO_STATE_READY:
            self.curinfo.inner = indent
            self.info_state = DuckParser.INFO_STATE_BLOCK

        self.info_state = DuckParser.INFO_STATE_BLOCK

        self.add_text(iline)

    def _parse_line_info_attr(self, line):
        self._attrparser.parse_line(line)
        if self._attrparser.finished:
            self.curinfo.attributes = self._attrparser.attributes

            remainder = self._attrparser.remainder.lstrip()
            if remainder != '':
                if not self.curinfo.is_leaf:
                    pnode = self.factory.create_info_paragraph_node(self.curinfo.outer)
                    self.curinfo.add_child(pnode)
                    self.curinfo = pnode
                self.set_text(remainder)
            self._attrparser = None
            if self._text == '':
                self.info_state = DuckParser.INFO_STATE_READY
            else:
                self.info_state = DuckParser.INFO_STATE_INFO

    def _parse_line_block(self, line):
        # Blank lines close off elements that have inline content (leaf)
        # unless they're verbatim elements that have an inner indent. Only
        # decreasing indent can break free of those. They also break out of
        # unindented block container elements, except for a set of special
        # elements that take lists of things instead of general blocks.
        if line.strip() == '':
            if self.current.is_leaf:
                if (self.current.is_verbatim and
                    self.current.inner > self.current.outer):
                    self.add_text('\n')
                else:
                    self.push_text()
                    self.current = self.current.parent
            while self.current.inner == self.current.outer:
                if isinstance(self.current, (Division, Document)):
                    break
                if self.current.is_greedy:
                    break
                if self.current.is_leaf:
                    self.push_text()
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
            self.push_text()
            while not isinstance(self.current, (Division, Document)):
                self.current = self.current.parent
            while self.current.divdepth >= sectd:
                self.current = self.current.parent
            if sectd != self.current.divdepth + 1:
                if isinstance(self.current, Document) and (
                        self._fragments and(
                            len(self.current.children) == 0 or
                            sectd == self.current.children[0].divdepth)):
                    pass
                else:
                    raise SyntaxError('Incorrect section depth', self)
            self.factory.handle_division_title(depth=sectd, inner=sectd+1)
            self.set_text(line[sectd + 1:])
            self.state = DuckParser.STATE_HEADER
            return

        # If the indent is less than what we can append to the current
        # node, unravel until we're at the same indent level. Note that
        # this still might not be the right level. We may or may not be
        # able to add children to a block at the same indent, but we'll
        # handle that later, because it depends on stuff. We don't use
        # unravel, because that always breaks out of leafs, and at this
        # point we might still be adding text to a leaf.
        indent = DuckParser.get_indent(line)
        if indent < self.current.inner:
            self.push_text()
            while self.current.inner > indent:
                if isinstance(self.current, (Division, Document)):
                    break
                self.current = self.current.parent

        if self.current.is_verbatim:
            iline = line[self.current.inner:]
        else:
            iline = line[indent:]

        # [[[ starts a no-parse fence that ends with ]]], either at the
        # end of this line, or on its own line later. This just suppresses
        # block and inline parsing. It has no additional semantics. So if
        # we're not already in a leaf element, create a paragraph just as
        # we would do if we encountered normal text.
        if iline.startswith('[[['):
            self.push_text()
            node = Fence('_', indent, parser=self)

            if not (self.current.is_leaf or self.current.is_external or
                    (self.current.is_tree_item and not self.current.has_tree_items)):
                if self.current.is_tree_item:
                    while self.current.is_name(('tree', 'item')):
                        self.current = self.current.parent
                while self.current.outer == indent and not self.current.available:
                    if isinstance(self.current, (Division, Document)):
                        break
                    self.current = self.current.parent
                pnode = self.factory.create_block_paragraph_node(indent)
                self.current.add_child(pnode)
                pnode.add_child(node)
            else:
                self.current.add_child(node)

            sline = iline.strip()[3:]
            if sline.endswith(']]]'):
                node.inner = 0
                node.add_line(sline[:-3] + '\n')
            else:
                if sline.strip() != '':
                    node.inner = 0
                    node.add_line(sline + '\n')
                self.current = node
                self._fenced = True
            return

        # Give all extensions a shot at this line. If any of them handles
        # the line (returns True), we're done.
        for extension in self.extensions:
            if extension.parse_line_block(line):
                return

        if iline.startswith('['):
            # Start a block with a standard block declaration.
            self.push_text()

            for j in range(1, len(iline)):
                if not _isnmtoken(iline[j]):
                    break
            name = iline[1:j]
            node = self.factory.create_block_node(name, indent)

            if node.is_name('item'):
                self.unravel_for_list_item(indent)
            elif node.is_name(('td', 'th')):
                self.unravel_for_table_cell(indent)
            elif node.is_name('tr'):
                self.unravel_for_table_row(indent)
            elif node.is_name(('thead', 'tfoot', 'tbody')):
                self.unravel_for_table_body(indent)
            else:
                self.unravel_for_block(indent)

            if iline[j] == ']':
                self.state = DuckParser.STATE_BLOCK_READY
                self._take_block_node(node)
            else:
                self._attrparser = AttributeParser(self, node=node)
                self._attrparser.parse_line(iline[j:])
                if self._attrparser.finished:
                    node.attributes = self._attrparser.attributes
                    self.state = DuckParser.STATE_BLOCK_READY
                    self._attrparser = None
                    self._take_block_node(node)
                else:
                    self.state = DuckParser.STATE_BLOCK_ATTR
        elif iline.startswith('. '):
            self._parse_line_block_title(iline, indent)
        elif iline.startswith('- '):
            self._parse_line_block_item_title(iline, indent)
        elif iline.startswith('* '):
            self._parse_line_block_item_content(iline, indent)
        elif not (self.current.is_leaf or self.current.is_external or
                  (self.current.is_tree_item and not self.current.has_tree_items)):
            if self.current.is_tree_item:
                while self.current.is_name(('tree', 'item')):
                    self.current = self.current.parent
            while self.current.outer == indent and not self.current.available:
                if isinstance(self.current, (Division, Document)):
                    break
                self.current = self.current.parent
            node = self.factory.create_block_paragraph_node(indent)
            self.current.add_child(node)
            self.current = node
            self.add_text(iline)
        else:
            self.add_text(iline)

    def _parse_line_block_title(self, iline, indent):
        # For lines starting with '. '. Creates a block title.
        self.push_text()
        self.unravel_for_block(indent)
        self.factory.handle_block_title(indent, indent + 2)
        self._parse_line((' ' * self.current.inner) + iline[2:])

    def _parse_line_block_item_title(self, iline, indent):
        # For lines starting with '- '. It might be a th element,
        # or it might be a title in a terms item. It might also
        # start a terms element.
        self.push_text()
        self.unravel_for_indent(indent)
        self.factory.handle_block_item_title(indent, indent + 2)
        self._parse_line((' ' * self.current.inner) + iline[2:])

    def _parse_line_block_item_content(self, iline, indent):
        # For lines starting with '* '. It might be a td element,
        # it might be an item element in a list or steps, it might
        # be a tree item, or it might start the content of an item
        # in a terms. It might also start a list element.
        self.push_text()
        self.unravel_for_indent(indent)
        node = self.factory.handle_block_item_content(indent, indent + 2)
        self._parse_line((' ' * node.inner) + iline[2:])

    def _parse_line_block_attr(self, line):
        self._attrparser.parse_line(line)
        if self._attrparser.finished:
            node = self._attrparser.node
            node.attributes = self._attrparser.attributes
            self.state = DuckParser.STATE_BLOCK_READY
            self._attrparser = None
            self._take_block_node(node)

    def _parse_line_block_ready(self, line):
        indent = DuckParser.get_indent(line)
        if indent < self.current.outer:
            while self.current.outer > indent:
                if isinstance(self.current, (Division, Document)):
                    break
                self.current = self.current.parent
        else:
            if line.lstrip().startswith('@'):
                self.info_state = DuckParser.INFO_STATE_INFO
            self.current.inner = DuckParser.get_indent(line)
        self.state = DuckParser.STATE_BLOCK
        self._parse_line(line)

    def _take_block_node(self, node):
        if node.extension:
            for extension in self.extensions_by_module[node.extension]:
                if extension.take_block_node(node):
                    return
            # If no extension claimed it, but there's still a namespace
            # binding, that's ok. You can have a namespace prefix with
            # the same name as an extension, but the extension wins.
            if node.nsuri is not None:
                self.current.add_child(node)
                self.current = node
            else:
                raise SyntaxError('Unrecognized extension element: ' + node.name, self)
        else:
            self.current.add_child(node)
            self.current = node

    def set_text(self, text):
        self._text = text

    def add_text(self, text):
        self._text += text

    def push_text(self):
        if self._text != '':
            if self.info_state != DuckParser.INFO_STATE_NONE:
                self.curinfo.add_text(self._text)
            else:
                self.current.add_text(self._text)
            self.set_text('')

    # Call this if you have an item to insert
    def unravel_for_list_item(self, indent):
        self.unravel_for_indent(indent)
        while self.current.outer == indent:
            if isinstance(self.current, (Division, Document)):
                break
            if self.current.available:
                break
            if self.current.is_list:
                break
            self.current = self.current.parent

    # Call this if you have a td or th to insert
    def unravel_for_table_cell(self, indent):
        self.unravel_for_indent(indent)
        while self.current.outer == indent:
            if isinstance(self.current, (Division, Document)):
                break
            if self.current.available:
                break
            if self.current.is_name('tr'):
                break
            self.current = self.current.parent
        if self.current.is_tree_item:
            while self.current.is_name(('tree', 'item')):
                self.current = self.current.parent

    # Call this if you have a tr to insert
    def unravel_for_table_row(self, indent):
        self.unravel_for_indent(indent)
        while self.current.outer == indent:
            if isinstance(self.current, (Division, Document)):
                break
            if self.current.available:
                break
            if self.current.is_name(('table', 'thead', 'tfoot', 'tbody')):
                break
            self.current = self.current.parent
        if self.current.is_tree_item:
            while self.current.is_name(('tree', 'item')):
                self.current = self.current.parent

    # Call this if you have a tbody, thead, or tfoot to insert
    def unravel_for_table_body(self, indent):
        self.unravel_for_indent(indent)
        while self.current.outer == indent:
            if isinstance(self.current, (Division, Document)):
                break
            if self.current.available:
                break
            if self.current.is_name('table'):
                break
            self.current = self.current.parent
        if self.current.is_tree_item:
            while self.current.is_name(('tree', 'item')):
                self.current = self.current.parent

    # Call this if you have any other block to insert
    def unravel_for_block(self, indent):
        self.unravel_for_indent(indent)
        while self.current.outer == indent:
            if isinstance(self.current, (Division, Document)):
                break
            if self.current.available:
                break
            self.current = self.current.parent
        if self.current.is_tree_item:
            while self.current.is_name(('tree', 'item')):
                self.current = self.current.parent

    # This only unravels what indentation absolutely forces.
    def unravel_for_indent(self, indent):
        while self.current.outer > indent or self.current.is_leaf:
            if isinstance(self.current, (Division, Document)):
                break
            self.current = self.current.parent


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
