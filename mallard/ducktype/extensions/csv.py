# Copyright (c) 2019 Shaun McCance <shaunm@gnome.org>
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

# FIXME:
# * Copy over attributes from ext node to table node
# * Except maybe we want some ext attrs:
#   * Ext attr to change separator char? (csv:sep=tab)
#   * Ext attr to control row and col headers?
#   * Ext attr to parse lines inline? Or should that be default?
# * Set inner indent to allow newlines?

class CsvExtension(mallard.ducktype.parser.ParserExtension):
    def __init__(self, parser, prefix, version):
        if version == 'experimental':
            self.version = version
        else:
            raise mallard.ducktype.parser.SyntaxError(
                'Unsupported csv extension version: ' + version,
                parser)
        self.parser = parser
        self.prefix = prefix
        self.version = version
        self.table = None

    def take_block_node(self, node):
        if node.name != 'csv:table':
            return False
        self.table = mallard.ducktype.parser.Block('table')
        # Normally table elements are "greedy", meaning they have special
        # rules that allow them to consume more stuff at the same indent
        # level. These tables, however, are different. Turn off greedy to
        # let the parser do its job.
        self.table.is_greedy = False
        self.parser.current.add_child(self.table)
        self.parser.current = self.table
        return True

    def parse_line_block(self, line):
        if self.table is None:
            return False
        else:
            if self.table is not self.parser.current:
                self.table = None
                return False
        tr = mallard.ducktype.parser.Block('tr')
        self.parser.current.add_child(tr)
        cells = line.split(',')
        for cell in cells:
            td = mallard.ducktype.parser.Block('td')
            tr.add_child(td)
            tdp = mallard.ducktype.parser.Block('p')
            td.add_child(tdp)
            tdp.add_text(cell)
        return True
