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

################################################################################
# This is a test extension. Its primary purpose is to fuel regression tests.
# Since it exercises all the extension points, it's heavily commented so you
# can learn from it.

import mallard.ducktype

# All extensions are a subclass of ParserExtension. When the parser encounters an
# extension declaration like foo/1.0, it imports mallard.ducktype.extensions.foo
# and tries to instantiate every ParserExtension subclass in it. It doesn't matter
# what you name your classes.

class TestExtension(mallard.ducktype.parser.ParserExtension):
    def __init__(self, parser, prefix, version):
        # Usually you'd use this to specify a version to make sure this code is
        # compatible with what the document expects. In this case, though, we're
        # using the version to specify which bit of text extension to use.
        if version == 'block':
            self.mode = 'block'
        else:
            raise mallard.ducktype.parser.SyntaxError(
                'Unsupported testing extension version: ' + version,
                parser)
        self.parser = parser
        self.prefix = prefix
        self.version = version
        # Feel free to do things to the parser or the document root here.
        self.parser.document.add_namespace('test', 'http://projectmallard.org/test/')

    def parse_line_block(self, line):
        # This is the function to implement do things in a block context,
        # like adding a shorthand notation for a block element. It gets
        # called only in places where a regular block element could occur.
        # Headers, comments, and fences have already been taken care of.
        if self.mode != 'block':
            return False

        indent = mallard.ducktype.parser.DuckParser.get_indent(line)
        iline = line[indent:]

        # Return False to indicate you're not handling this line. For
        # this test, we're doing something with lines that start with
        # three asterisks and a space.
        if not iline.startswith('*** '):
            return False

        # In most cases when creating block elements, you'll want to start
        # by calling push_text and unravel_for_block. push_text makes sure
        # any text lines we just encountered get put into a block element.
        # unravel_for_block gets you to the correct current element to start
        # adding new block elements, based on indentation and the standard
        # block nesting rules. There are other unravel functions for special
        # nesting rules for tables and lists.
        self.parser.push_text()
        self.parser.unravel_for_block(indent)

        # Here's the meat of what this extension does. It creates a block
        # element, adds an attribute to it, adds the element to the current
        # element (which unravel_for_block got us to), then sets the new
        # element as the current element. Setting the new element as the
        # current element lets the parser add content to it. If you want
        # to add something that doesn't take content, don't set it as
        # current.
        qnode = mallard.ducktype.parser.Block('test:TEST', indent, parser=self.parser)
        qnode.attributes = mallard.ducktype.parser.Attributes()
        qnode.attributes.add_attribute('line', iline[4:].strip())
        self.parser.current.add_child(qnode)
        self.parser.current = qnode

        # This lets the parser know that we've just created a block element
        # and it's ready to take on new content. This is important because
        # the first child element will set the inner indent of our new block
        # element. Don't bother with this if you're adding something that
        # doesn't take content (and you didn't set as current).
        self.parser.state = mallard.ducktype.parser.DuckParser.STATE_BLOCK_READY

        # Return True to indicate you have handled the line. The parser will
        # stop trying to do anything else with this line.
        return True
