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
        # using the version to specify which parts of the test extension to use.
        if version == 'block':
            self.mode = 'block'
        elif version == 'blocknode':
            self.mode = 'blocknode'
        elif version == 'directive':
            self.mode = 'directive'
        else:
            raise mallard.ducktype.parser.SyntaxError(
                'Unsupported _test extension version: ' + version,
                parser)
        # It's important to bear in mind that parser might not always be a
        # DuckParser object. Depending on the extension and where it's used,
        # parser might be something like a DirectiveIncludeParser or an
        # InlineParser.
        self.parser = parser
        self.prefix = prefix
        self.version = version
        # Feel free to do things to the parser or the document root here.
        self.parser.document.add_namespace('test', 'http://projectmallard.org/test/')

    def parse_line_block(self, line):
        # This is the function to implement to do things in a block context,
        # like adding a shorthand notation for a block element. It gets
        # called only in places where a regular block element could occur.
        # Headers, comments, and fences have already been taken care of.
        # If you want to add a block extension with a syntax that looks
        # like a standard block declaration, use take_block_node instead.
        # That method will handle a lot more things for you.
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

    def take_block_node(self, node):
        # This is the function to implement to do things with extension
        # elements that looks like block nodes. It gets called on a Node
        # object that has alredy been parsed as if it were a block node,
        # but it has not been added to the document. This will only be
        # called for nodes with a prefix matching the base name of your
        # extension. For example, this extension is _test.py, so it will
        # be called for things like:
        #   [_test:block]
        #   [_test:frobnicate]
        # It will not be called for things like:
        #   [test:block]
        #   [_test_frobnicate]
        # If you want to add block syntax that doesn't look like a
        # standard block declaration, use parse_line_block instead.
        if self.mode != 'blocknode':
            return False

        # Return False to indicate you're not handling this node. If no
        # extensions handle the node, the parser will try to treat it
        # as a regular block node, requiring a suitable namespace prefix
        # binding. If it can't find one, it will raise an error. For this
        # test, we're doing something with block declarations that look
        # like [_test:block]
        if node.name != '_test:block':
            return False

        # If you read the comments on parse_line_block, you might be tempted
        # to call push_text and unravel_for_block here. But you don't have
        # to. The parser has already parsed this thing as if it were a block
        # declaration, and that includes pushing text and unraveling.

        # Here's the meat of what this extension does. Instead of allowing
        # the passed-in node to go into the document, it creates a new node.
        # It copies over the attributes from the extension block element,
        # and even adds its own attribute value. You could do completely
        # different things with the attributes. If you want to add something
        # that doesn't take content, don't set it as current.
        qnode = mallard.ducktype.parser.Block('note', outer=node.outer, parser=self.parser)
        qnode.attributes = mallard.ducktype.parser.Attributes()
        # It's safe to add a style attribute and then add other attributes
        # without checking their names. Attributes objects automatically
        # join multiple style and type attributes into space-separated lists.
        qnode.attributes.add_attribute('style', 'warning')
        if node.attributes is not None:
            for attr in node.attributes.get_attributes():
                qnode.attributes.add_attribute(attr, node.attributes.get_attribute(attr))
        self.parser.current.add_child(qnode)
        self.parser.current = qnode

        # If you read the comments on parse_line_block, you might be tempted
        # to set self.parser.state here. Don't bother, unless you actually
        # really need to set it to something other than STATE_BLOCK_READY.
        # The parser has already entered that state by the time extensions
        # get a crack at block declarations.

        # Return True to indicate you have handled the node. The parser will
        # stop trying to do anything else with this node.
        return True

    def take_directive(self, directive):
        # This is the function to implement to handle parser directives at
        # the top of a file. This will only be called for directives with
        # a prefix matching the base name of your extension. For example,
        # this extension is _test.py, so it will be called for things like:
        #   @_test:defines
        #   @_test:frobnicate
        # It will not be called for things like:
        #   @test:defines
        #   @_test_frobnicate
        if self.mode != 'directive':
            return False

        if directive.name == '_test:defines':
            # This extension recognizes a simple directive like this:
            #   @_test:defines
            # And treats it like it defined something lengthier. Just add
            # that definition to the main document, and we're done. For a
            # directive parser extension, the calling parser might be a
            # DirectiveIncludeParser instead of a DuckParser. But that's
            # OK, because DirectiveIncludeParser also has a document
            # attribute that points to the right place.
            self.parser.document.add_definition('TEST',
                                                'This is a $em(test). ' +
                                                'It is only a $em[.strong](test).')
            # Return True to tell the parser we handled this directive.
            return True
        else:
            return False
