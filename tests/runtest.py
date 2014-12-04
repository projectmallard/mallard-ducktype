import os
import sys
import ducktype

try:
    parser = ducktype.DuckParser()
    parser.parse_file(sys.argv[1])
    parser.finish()
except ducktype.SyntaxError as e:
    print(os.path.basename(e.filename) + ':' +
          str(e.linenum) + ': ' + e.message)
    sys.exit(1)
parser.document.write_xml(sys.stdout)
