import os.path


def FIXME(msg=None):
    if msg is not None:
        print('FIXME: %s' % msg)
    else:
        print('FIXME')


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

    def print(self):
        for attr in self._attrlist:
            print(' ' + attr + '="', end='')
            if attr == 'style':
                print(' '.join(self._attrvals[attr]), end='')
            else:
                print(self._attrvals[attr], end='')
            print('"', end='')


class Block:
    def __init__(self, name, indent=0):
        self.name = name
        self.indent = indent
        self.children = []
        self.attributes = None
        self.division = (name in ('page', 'section'))
        self.verbatim = (name in ('screen', 'code'))
        self.list = (name in ('list', 'steps', 'terms', 'tree'))
        self.terminal = (name in
                         ('p', 'screen', 'code', 'title',
                          'subtitle', 'desc', 'cite'))
        self._parent = None
        self._depth = 1

    @property
    def empty(self):
        return len(self.children) == 0

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
        self.children.append(child)
        child.parent = self

    def add_text(self, text):
        self.children.append(text)

    def print(self, depth=0):
        if self.name == 'page':
            print('<?xml version="1.0" encoding="utf-8"?>')
        print((' ' * depth) + '<' + self.name, end='')
        if self.name == 'page':
            print(' xmlns="http://projectmallard.org/1.0/"', end='')
        if self.attributes is not None:
            self.attributes.print()
        if self.empty:
            print('/>')
        elif isinstance(self.children[0], Block):
            print('>')
        else:
            print('>', end='')
        for i in range(len(self.children)):
            child = self.children[i]
            if isinstance(child, Block):
                child.print(depth=depth+1)
            else:
                lines = child.split('\n')
                while lines[-1] == '':
                    lines.pop()
                for j in range(len(lines)):
                    line = lines[j]
                    if not (i == 0 and j == 0) and not self.verbatim:
                        line = (' ' * depth) + line
                    if not (i + 1 == len(self.children) and j + 1 == len(lines)):
                        line = line + '\n'
                    print(line, end='')
        if not self.empty:
            if isinstance(self.children[0], Block):
                print((' ' * depth), end='')
            print('</' + self.name + '>')


class SyntaxError(Exception):
    pass


class AttributeParser:
    def __init__(self):
        self.remainder = None
        self.attributes = Attributes()
        self.finished = False
        self._quote = None
        self._value = ''
        self._attrname = None

    def parse_line(self, line):
        i = 0
        while i < len(line) and not self.finished:
            if self._quote is not None:
                j = i
                while j < len(line):
                    if line[j] == '&':
                        FIXME()
                    elif line[j] == self._quote:
                        self._value += line[i:j]
                        self.attributes.add_attribute(self._attrname, self._value)
                        self._value = ''
                        self._quote = None
                        i = j
                        break
                    else:
                        j += 1
                i += 1
            elif line[i].isspace():
                i += 1
            else:
                if line[i] == ']':
                    self.finished = True
                    self.remainder = line[i + 1:]
                elif line[i] in ('.', '#'):
                    j = i + 1
                    while j < len(line) and _isnmtoken(line[j]):
                        j += 1
                    word = line[i + 1:j]
                    if line[i] == '.':
                        self.attributes.add_attribute('style', word)
                    else:
                        self.attributes.add_attribute('id', word)
                    i = j
                elif line[i] == '>':
                    i += 1
                    FIXME()
                else:
                    j = i + 1
                    while j < len(line) and _isnmtoken(line[j]):
                        j += 1
                    word = line[i:j]
                    if line[j] == '=':
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
                            self.attributes.add_attribute(word, line[j + 1:k])
                            i = k
                    elif line[j].isspace() or line[j] == ']':
                        self.attributes.add_attribute('type', line[i:j])
                        i = j
                        if line[j] == ']':
                            pass
                    else:
                        raise SyntaxError()


class DuckParser:
    STATE_TOP = 1
    STATE_HEADER = 2
    STATE_HEADER_POST = 3
    STATE_SUBHEADER = 4
    STATE_SUBHEADER_POST = 5
    STATE_HEADER_ATTR = 6
    STATE_HEADER_ATTR_POST = 7
    STATE_HEADER_INFO = 8
    STATE_BLOCK = 9
    STATE_BLOCK_ATTR = 10
    STATE_BLOCK_READY = 11
    STATE_BLOCK_INFO = 12

    def __init__(self):
        self.state = DuckParser.STATE_TOP
        self.document = Block('page')
        self.current = self.document
        self._value = ''
        self._attrparser = None
        self._defaultid = None

    def parse_file(self, filename):
        self._defaultid = os.path.basename(filename)
        if self._defaultid.endswith('.duck'):
            self._defaultid = self._defaultid[:-5]
        fd = open(filename)
        for line in fd:
            self.parse_line(line)
        fd.close()

    def parse_line(self, line):
        self._parse_line(line)

    def finish(self):
        self._push_value()
        if self._defaultid is not None:
            if self.document.attributes is None:
                self.document.attributes = Attributes()
            if 'id' not in self.document.attributes:
                self.document.attributes.add_attribute('id', self._defaultid)

    def _parse_line(self, line):
        if self.state == DuckParser.STATE_TOP:
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
            self._parse_line_header_post_info(line)
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
            pass
        elif line.startswith('= '):
            self._value = line[2:]
            node = Block('title', 2)
            self.current.add_child(node)
            self.current = node
            self.state = DuckParser.STATE_HEADER
        else:
            raise SyntaxError()

    def _parse_line_header(self, line):
        if line.startswith(' ' * self.current.indent):
            self._parse_line_header_attr_start(line)
        else:
            self._push_value()
            self.current = self.current.parent
            self.state = DuckParser.STATE_HEADER_POST
            self._parse_line(line)

    def _parse_line_header_post(self, line):
        if line.startswith(('-' * self.current.depth) + ' '):
            self._value = line[self.current.depth + 1:]
            node = Block('subtitle', self.current.depth + 1)
            self.current.add_child(node)
            self.current = node
            self.state = DuckParser.STATE_SUBHEADER
        elif line.startswith('@'):
            FIXME('header info')
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_subheader(self, line):
        if line.startswith(' ' * self.current.indent):
            self._parse_line_header_attr_start(line)
        else:
            self._push_value()
            self.current = self.current.parent
            self.state = DuckParser.STATE_SUBHEADER_POST
            self._parse_line(line)

    def _parse_line_subheader_post(self, line):
        if line.startswith('@'):
            FIXME('header info')
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_header_attr_start(self, line):
        iline = line[self.current.indent:]
        if iline.startswith('['):
            self._push_value()
            self.current = self.current.parent
            self._attrparser = AttributeParser()
            self._attrparser.parse_line(iline[1:])
            if self._attrparser.finished:
                self.current.attributes = self._attrparser.attributes
                self.state = DuckParser.STATE_HEADER_ATTR_POST
            else:
                self.state = DuckParser.STATE_HEADER_ATTR
        else:
            self._value += line[self.current.indent:]

    def _parse_line_header_attr(self, line):
        self._attrparser.parse_line(line)
        if self._attrparser.finished:
            self.current.attributes = self._attrparser.attributes
            self.state = DuckParser.STATE_HEADER_ATTR_POST

    def _parse_line_header_attr_post(self, line):
        if line.startswith('@'):
            FIXME('header info')
        else:
            self.state = DuckParser.STATE_BLOCK
            self._parse_line(line)

    def _parse_line_block(self, line):
        # Blank lines close off elements that have inline content (terminal)
        # unless they're verbatim elements that have an inner indent. Only
        # decreasing indent can break free of those.
        if line.strip() == '':
            if self.current.terminal:
                if (self.current.verbatim and
                    self.current.indent > self.current.parent.indent):
                    self._value += '\n'
                else:
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
            self._push_value
            while not self.current.division:
                self.current = self.current.parent
            while self.current.depth >= sectd:
                self.current = self.current.parent
            if sectd != self.current.depth + 1:
                raise SyntaxError()
            section = Block('section')
            self.current.add_child(section)
            title = Block('title', sectd + 1)
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
        if indent < self.current.indent:
            self._push_value()
            while (not self.current.division) and self.current.indent > indent:
                self.current = self.current.parent

        iline = line[self.current.indent:]
        if iline.startswith('['):
            # Start a block with a standard block declaration.
            self._push_value()
            while (not self.current.division and (
                    self.current.terminal or
                    self.current.parent.indent > indent)):
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
                    self.current.parent.indent == indent)):
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

            node = Block(name, indent)
            self.current.add_child(node)
            self.current = node

            if iline[j] == ']':
                self.state = DuckParser.STATE_BLOCK_READY
            else:
                self._attrparser = AttributeParser()
                self._attrparser.parse_line(iline[j:])
                if self._attrparser.finished:
                    self.current.attributes = self._attrparser.attributes
                    self.state = DuckParser.STATE_BLOCK_READY
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
                    self.current.parent.indent == indent)):
                self.current = self.current.parent
            node = Block('p', indent)
            self.current.add_child(node)
            self.current = node
            self._value += iline
        else:
            self._value += iline

    def _parse_line_block_title(self, iline, indent):
        self._push_value()
        while ((not self.current.division) and
               (self.current.terminal or self.current.parent.indent > indent)):
            self.current = self.current.parent
        title = Block('title', indent + 2)
        self.current.add_child(title)
        self.current = title
        self._parse_line((' ' * self.current.indent) + iline[2:])

    def _parse_line_block_item_title(self, iline, indent):
        self._push_value()
        while ((not self.current.division) and
               (self.current.terminal or self.current.parent.indent > indent)):
            self.current = self.current.parent

        if self.current.name == 'tr':
            node = Block('th', indent + 2)
            self.current.add_child(node)
            self.current = node
            self._parse_line((' ' * node.indent) + iline[2:])
            return

        if self.current.name != 'terms':
            node = Block('terms', indent)
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
            item = Block('item', indent + 2)
            self.current.add_child(item)
            self.current = item
        title = Block('title', indent + 2)
        self.current.add_child(title)
        self.current = title
        self._parse_line((' ' * self.current.indent) + iline[2:])

    def _parse_line_block_item_content(self, iline, indent):
        self._push_value()
        while ((not self.current.division) and
               (self.current.terminal or self.current.parent.indent > indent)):
            self.current = self.current.parent

        if self.current.name == 'tr':
            node = Block('td', indent + 2)
            self.current.add_child(node)
            self.current = node
            self._parse_line((' ' * node.indent) + iline[2:])
        elif self.current.name == 'terms':
            # All the logic above will have unraveled us from the item
            # created by the title, so we have to step back into it.
            if self.current.empty or self.current.children[-1].name != 'item':
                raise SyntaxError()
            self.current = self.current.children[-1]
            self._parse_line((' ' * self.current.indent) + iline[2:])
        elif self.current.name == 'tree':
            FIXME(self.current.name)
        elif self.current.name in ('list', 'steps'):
            item = Block('item', indent + 2)
            self.current.add_child(item)
            self.current = item
            self._parse_line((' ' * item.indent) + iline[2:])
        else:
            node = Block('list', indent)
            self.current.add_child(node)
            item = Block('item', indent + 2)
            node.add_child(item)
            self.current = item
            self._parse_line((' ' * item.indent) + iline[2:])

    def _parse_line_block_attr(self, line):
        self._attrparser.parse_line(line)
        if self._attrparser.finished:
            self.current.attributes = self._attrparser.attributes
            self.state = DuckParser.STATE_BLOCK_READY

    def _parse_line_block_ready(self, line):
        if not line.startswith(' ' * self.current.indent):
            FIXME()
            return
        self.current.indent = self._get_indent(line)
        self.state = DuckParser.STATE_BLOCK
        self._parse_line(line)

    def _get_indent(self, line):
        for i in range(len(line)):
            if line[i] != ' ':
                return i

    def _push_value(self):
        if self._value != '':
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


if __name__ == '__main__':
    import sys
    parser = DuckParser()
    parser.parse_file(sys.argv[1])
    parser.finish()
    parser.document.print()
