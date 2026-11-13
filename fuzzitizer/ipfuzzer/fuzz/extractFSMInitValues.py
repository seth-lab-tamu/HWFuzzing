import os, re
import traceback
import pyverilog.vparser.ast as pyast
from pyverilog.dataflow.visit import NodeVisitor
import pyverilog.vparser.parser as pyparser

"""
- There could be bloks with no begin or end
  - ex: always_comb running_uds = (doe_cmd_reg.cmd == DOE_UDS);
"""
def trimBlockEnd(block, debug=False): 
  # assumes that block will have begin and end
  lines = block.splitlines(True)
  lastEndLine = None
  firstBeginLine = -1
  numBegins = 0
  # first find atleast one begin
  for i, l in enumerate(lines): 
    if re.search(r"\bend\b", l): # there shouldnt be end before begin
      assert True, f"found end before begin, {lines}"
    if re.search(r"\bbegin\b", l):
      numBegins = 1
      firstBeginLine = i
      break
  #assert firstBeginLine > -1, f"coundnt find any line with begin, {lines}"
  if firstBeginLine == -1: # no begin in the block
    return lines
  # keep looking for ends for each begin
  # note that same like can have both begin and end: "end else begin"
  for i, l in enumerate(lines[firstBeginLine+1:], start=firstBeginLine+1): 
    if re.search(r"\bbegin\b", l):
      numBegins += 1
    if re.search(r"\bend\b", l):
      if numBegins == 1: # found the last end
        lastEndLine = i; break
      else: numBegins -= 1
  assert lastEndLine, f"coundnt find any line with end, {lines}"
  return lines[:lastEndLine+1]
  

"""
- Creates a stripped down copy of the input file and tries parsing this file
- Everything other than always blocks is stripped out
- Since all info we want is inside always blocks, this shouldnt effect the code
"""
def strippedPyverilogParse(inputFile, debug=False): 
  with open(inputFile, 'r') as fp: origData = fp.read()

  # remove all comments to prevent unintentional grabs
  commPattern = r'//.*?$|/\*.*?\*/|/\*(.|\n)*?\*/'
  origData = re.sub(commPattern, '', origData, flags=re.DOTALL | re.MULTILINE)

  # break the file by module declarations
  origLines = origData.splitlines()
  modules = {}
  moduleLines = []
  moduleName = None
  replacedLines = []
  for i, line in enumerate(origLines): 
    if re.search(r'\bmodule\b', line):  # new module
      assert moduleLines == [], f"found module inside module, {inputFile}, {i}, {line}"
      lineData = re.search(r'\bmodule\b\s*\b(.*)\b', line)
      moduleName = lineData.group(1)
      moduleLines.append(line)
    elif re.search(r'\bendmodule\b', line): # end module
      if moduleLines != []: # save module
        moduleLines.append(line)
        modules[moduleName] = moduleLines
        moduleLines = []
        moduleName = None # this indicates we are outside module now
    else: 
      if moduleName: # inside some module
        moduleLines.append(line)

  for moduleName, moduleLines in modules.items():
    modules[moduleName] = '\n'.join(moduleLines)

  # extract all always blocks using begin as keyword for each module
  for moduleName, moduleData in modules.items():
    alwaysPattern = r'\n(\s*always(?:.|[\s\n])*?)(?=\n\s*always|\Z)'
    ### see if there is any for loop
    forPattern = r'\n(\s*for(?:.|[\s\n])*?)(?=\n\s*for|\Z)'
    forBlocks = re.findall(forPattern, moduleData)
    
    # remove any text after end keyword
    forBlocks = [''.join(trimBlockEnd(fb, debug)) for fb in forBlocks]

    # remove the for blocks with always blocks in them
    for forBlock in forBlocks: 
      alwaysBlocks = re.findall(alwaysPattern, forBlock)
      if alwaysBlocks: 
        moduleData = moduleData.replace(forBlock, '\n')

    ### find always blocks
    alwaysBlocks = re.findall(alwaysPattern, moduleData)
    
    # remove any text after the end keyword
    alwaysBlocks = [trimBlockEnd(ab, debug) for ab in alwaysBlocks]

    # clean the blocks
    cleans = []
    cleans.append([r'(\w+::)', '']) # replace any package references
    # replace any int unsigned
    # these shouldnt really be there since we trim stuff other than always blocks
    cleans.append([r'(parameter\s+int\s+unsigned)', 'parameter '])
    # replace any '0 with 0
    cleans.append([r"\s'(\d+)\b", r" \g<1>"])
    # replace any ++ with = + 1
    cleans.append([r"(\w+)\+\+", r" \g<1>=\g<1>+1"])

    for k, alwaysBlock in enumerate(alwaysBlocks): 
      for i, line in enumerate(alwaysBlock): 
        for clean in cleans: 
          if re.search(clean[0], line): 
            newLine = re.sub(clean[0], clean[1], line)
            replacedLines.append(f"\n//{line}//{newLine}")
            line = newLine
        alwaysBlock[i] = line
    
      alwaysBlocks[k] = ''.join(alwaysBlock)
    modules[moduleName] = alwaysBlocks
   
  # create the temp file
  tempFile = f"{inputFile}.back.sv"
  with open(tempFile, 'w') as fp: 
    for moduleName, alwaysBlocks in modules.items():
      fp.write(f"\nmodule {moduleName}();")
      fp.write('\n'.join(alwaysBlocks)) 
      fp.write(f"\nendmodule\n")
   
    if len(replacedLines) > 0: 
      fp.write("\n// the following lines are replaced;")
      for line in replacedLines: 
        fp.write(line)

  if debug: exit()

  return pyparser.parse([tempFile], preprocess_include=[os.path.dirname(tempFile)], preprocess_define=[])


def findNodesOfType(node, nodeType, recurse=False):
  childNodesofType = [i for i in node.children() if isinstance(i, nodeType)]
  if recurse: 
    for i in node.children(): 
      childNodesofType += findNodesOfType(i, nodeType, True)
  return childNodesofType


def findNodesOfTypeNodes(nodes, nodeType, recurse=False): 
  childNodesofType = []
  for node in nodes: 
    childNodesofType += findNodesOfType(node, nodeType, recurse)
  return childNodesofType


"""
getattr(object, name, default)
Return the value of the named attribute of object. name must be a string. If the string 
is the name of one of the object’s attributes, the result is the value of that attribute. 
For example, getattr(x, 'foobar') is equivalent to x.foobar. If the named attribute does 
not exist, default is returned if provided, otherwise AttributeError is raised. name need 
not be a Python identifier (see setattr()).


class NodeVisitor(object):
    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        for c in node.children():
            self.visit(c)
"""

class AdvNodeVisitor(NodeVisitor):
  
  def generic_visit(self, node):
    if node is None:
      return

    for c in node.children():
      self.visit(c)

class NodeFinder(AdvNodeVisitor):
  def __init__(self):
    self.always_blocks = []
    self.ifstatement_blocks = []
    self.block_blocks = []
    self.NonblockingSubstitution_blocks = []
    self.BlockingSubstitution_blocks = []
    self.Identifier_blocks = []
    self.ModuleDef_blocks = []
    self.Lvalue_blocks = []
    self.For_blocks = []

  def visit_Identifier(self, node):
    self.Identifier_blocks.append(node)
    self.generic_visit(node) 

  def visit_Always(self, node):
    self.always_blocks.append(node)
    self.generic_visit(node)

  def visit_Block(self, node):
    self.block_blocks.append(node)
    self.generic_visit(node)

  def visit_IfStatement(self, node):
    self.ifstatement_blocks.append(node)
    self.generic_visit(node)

  def visit_NonblockingSubstitution(self, node):
    self.NonblockingSubstitution_blocks.append(node)
    self.generic_visit(node)

  def visit_BlockingSubstitution(self, node):
    self.BlockingSubstitution_blocks.append(node)
    self.generic_visit(node)

  def visit_ModuleDef(self, node):
    self.ModuleDef_blocks.append(node)
    self.generic_visit(node)

  def visit_Lvalue(self, node): 
    self.Lvalue_blocks.append(node)
    self.generic_visit(node) 

  def visit_ForStatement(self, node): 
    self.For_blocks.append(node)


def extractModuleAst(modName, modFile, clkSubstrings, debug=False): 
  print(f"---------parsing {modName}, {modFile} file with pyverilog-----")
  if debug: print(modFile)

  # generate the ast 
  try: 
    ast, directives = pyparser.parse([modFile], preprocess_include=[os.path.dirname(modFile)], preprocess_define=[])
  except pyparser.ParseError as errorVar: 
    # since directly parsing dint work, try stripped down parsing
    print(f"WARNING: Failed to parse {modName}, {modFile} directly")
    print(f"Trying alternate parsing option")
    try: 
      ast, directives = strippedPyverilogParse(modFile)
    except pyparser.ParseError as errorVar : 
      if debug: 
        print(f"\n-----------------------------------Error traceback")
        print(traceback.format_exc())
        print(f"Pyverilog cannot parse {modName}, {modFile}, ignoring it!!")
        print(f"Error traceback done-----------------------------------\n")
      else: print(f"Pyverilog cannot parse {modName}, {modFile}, ignoring it!!")
      return None, None, None

  ### get the sequential always blocks in ast, we need them later
  modDef = None
  for i in ast.description.definitions: 
    if isinstance(i, pyast.ModuleDef) and i.name == modName: 
            # ignore modules other than target module
      modDef = i; break
  assert modDef, f"no module definition found for {mod.modName} in {mod.modFile}"
  if debug: modDef.show()

  alwaysNodes = findNodesOfType(modDef, pyast.Always)
  if debug: print(len(alwaysNodes))

  seqAlwaysNodes = []
  for node in alwaysNodes: 
    
    # get the signals in the sensitivity list
    sensListNodes = findNodesOfType(node, pyast.SensList)
    sensIdentifiers = findNodesOfTypeNodes(sensListNodes, pyast.Identifier, True)
    sensSignals = [i.name for i in sensIdentifiers]

    # see if atleast one of the signals has atleast one clock substrings, store this signal
    matchingClks = []
    for clkSubString in clkSubstrings: 
      matchingClks += [s for s in sensSignals if clkSubString in s]
    if matchingClks != []: 
      assert len(matchingClks) == 1, f"more than one clock signals in the sens list, handle this case!!, {matchingClks}, {mod.modName}"

      # visit the node and save info
      nodeBlocks = NodeFinder()
      nodeBlocks.generic_visit(node)
      seqAlwaysNodes.append([node, matchingClks[0], nodeBlocks])
  if debug: print(len(seqAlwaysNodes))

  return ast, directives, seqAlwaysNodes


