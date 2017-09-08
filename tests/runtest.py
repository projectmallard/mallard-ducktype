#!/usr/bin/env python3

import os
import sys

sys.path.insert(0, (os.path.dirname(os.path.abspath(os.path.dirname(sys.argv[0])))))

import mallard.ducktype

try:
    parser = mallard.ducktype.DuckParser()
    parser.parse_file(sys.argv[1])
    parser.finish()
except mallard.ducktype.SyntaxError as e:
    print(e.fullmessage)
    sys.exit(1)
parser.document.write_xml(sys.stdout)
