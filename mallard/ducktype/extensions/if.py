# Copyright (c) 2018 Shaun McCance <shaunm@gnome.org>
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

import mallard.ducktype

IFURI = 'http://projectmallard.org/if/1.0/'

class IfExtension(mallard.ducktype.parser.ParserExtension):
    def __init__(self, parser, prefix, version):
        if version == 'experimental':
            self.version = version
        else:
            raise mallard.ducktype.parser.SyntaxError(
                'Unsupported if extension version: ' + version,
                parser)
        self.parser = parser
        self.prefix = prefix
        self.version = version
        self.parser.document.add_namespace('if', IFURI)

    def parse_line_block(self, line):
        indent = mallard.ducktype.parser.DuckParser.get_indent(line)
        iline = line[indent:]

        if iline.strip() == '??':
            self.parser.push_text()
            self.parser.unravel_for_block(indent)

            if self.parser.current.is_name('choose', IFURI):
                elname = 'if:else'
            else:
                elname = 'if:choose'

            qnode = mallard.ducktype.parser.Block(elname, indent, parser=self.parser)
            self.parser.current.add_child(qnode)
            self.parser.current = qnode

            self.parser.state = mallard.ducktype.parser.DuckParser.STATE_BLOCK_READY
            return True

        if iline.startswith('? '):
            self.parser.push_text()
            self.parser.unravel_for_block(indent)

            if self.parser.current.is_name('choose', IFURI):
                elname = 'if:when'
            else:
                elname = 'if:if'

            qnode = mallard.ducktype.parser.Block(elname, indent, parser=self.parser)
            qnode.attributes = mallard.ducktype.parser.Attributes()
            qnode.attributes.add_attribute('test', iline[2:].strip())
            self.parser.current.add_child(qnode)
            self.parser.current = qnode

            self.parser.state = mallard.ducktype.parser.DuckParser.STATE_BLOCK_READY
            return True

        return False
