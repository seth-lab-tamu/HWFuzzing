
import os, re
from os.path import join, exists
import gzip
from string import Template
import xml.etree.ElementTree as et
from pyverilog.vparser.ast import Always, IfStatement, NonblockingSubstitution, Identifier, IntConst
from pyverilog.dataflow.visit import NodeVisitor

from pyverilog.vparser.parser import parse
import config
from configManager import getCONFIG
from extractFSMInitValues import NodeFinder, extractModuleAst

def convertVerilogValueToInt(verilogValue): 
  if "'" in verilogValue: 
    if verilogValue[0] != "'":
      verilogValueData = re.search(r"[\d]*('[a-z][\d]*)", verilogValue)
      verilogValue = verilogValueData.group(1)
    if verilogValue[1] == 'd': 
      return int(verilogValue[2:])
    elif verilogValue[1] == 'h': 
      return int(verilogValue[2:], 16)
    elif verilogValue[1] == 'b': 
      return int(verilogValue[2:], 2)
    else: 
      assert True, f"unknown number representation found, {verilogValue}"
  else:
    return int(verilogValue)


class FSMFSMNode(object):
  def __init__(self, fsmFsmNode, modName, fsmInst, fsmStateReg, fsmInitValue, fsmClk, debug=False, fsmRst=None):
    self.modName = modName
    self.modAst = None
    self.modSeqAlwaysNodes = None
    self.fsmInst = fsmInst 
    self.fsmFsmNode = fsmFsmNode 
    self.stateWidth = self.fsmFsmNode.attrib['width']
    self.fsmLineNo = self.fsmFsmNode.attrib['line']
    self.identifiedStates = {}
    self.identifiedTransitions = {'fromto': {}, 'tofrom': {}}
    self.identifiedTransitionsHex = []
    self.identifiedStateValues = []
    self.identifiedStateValuesHex = []
    self.unIdentifiedStateValues = []
    self.unIdentifiedStateValuesHex = []
    self.unIdentifiedStateValuesStr = ""
    self.fsmStateReg = fsmStateReg
    self.fsmInitValue = fsmInitValue 
    self.undefined_transitions_hex = []
    self.IDLE = None
    self.fsmClk = fsmClk
    self.fsmRst = fsmRst
    self.illeg_transitions_hex = []


  def parse_fsmfsm(self, debug=False):
    
    stateNodes = self.fsmFsmNode.findall('state')
    self.identifiedStates = {sn.attrib['id']: {k: v for k,v in sn.items()} \
                                  for sn in stateNodes}
    
    allPossibleStateValues = [i for i in range(2 ** int(self.stateWidth))]
    for i, d in self.identifiedStates.items(): 
      if d['value'] == 'parameterized': 
        d['absValue'] = int(self.fsmInst['params'][d['name']])
      else:
        d['absValue'] = int(d['value'], 16)
  
      assert d['absValue'] in allPossibleStateValues, f"fsm identified state value not in all possible state values, {self.fsmLineNo}, {self.fsmInst}, {i},{d}, {self.stateWidth}"
    if debug: print("identified states:", self.identifiedStates)
    

    transitionNodes = self.fsmFsmNode.findall('transition')
    self.identifiedTransitions['fromto'] = {sid: [] for sid in self.identifiedStates.keys()}
    self.identifiedTransitions['tofrom'] = {sid: [] for sid in self.identifiedStates.keys()}
    for tn in transitionNodes:
      self.identifiedTransitions['fromto'][tn.attrib['fromid']].append(tn.attrib['toid'])
      self.identifiedTransitions['tofrom'][tn.attrib['toid']].append(tn.attrib['fromid'])
      fromInt = self.identifiedStates[tn.attrib['fromid']]['absValue']
      toInt = self.identifiedStates[tn.attrib['toid']]['absValue']
      fromHex = f"{self.stateWidth}'h{hex(fromInt)[2:]}"
      toHex   = f"{self.stateWidth}'h{hex(toInt)[2:]}"
      self.identifiedTransitionsHex.append([fromHex, toHex])
    if debug: print("identified transitions:", self.identifiedTransitions)
    if debug: print("identified transitions hex:", self.identifiedTransitionsHex)
 

  def ident_undef_states(self, debug=False):
    allPossibleStateValues = [i for i in range(2 ** int(self.stateWidth))]
  
    self.identifiedStateValues = [s['absValue'] for s in self.identifiedStates.values()]
    self.unIdentifiedStateValues = [i for i in allPossibleStateValues\
                                            if not i in self.identifiedStateValues]
    self.identifiedStateValuesHex = [f"{self.stateWidth}'h{hex(v)[2:]}"\
                                    for v in self.identifiedStateValues]
    self.unIdentifiedStateValuesHex = [f"{self.stateWidth}'h{hex(v)[2:]}"\
                                    for v in self.unIdentifiedStateValues]
    self.unIdentifiedStateValuesStr = ",".join(self.unIdentifiedStateValuesHex)
    if debug: print("undefined state values:", self.unIdentifiedStateValues)


  def ident_undef_state_trans(self, debug=False):
    if len(self.unIdentifiedStateValues) == 0:
      self.undefined_transitions_hex = []; return

    for def_state in self.identifiedStateValuesHex:
      self.undefined_transitions_hex.append(\
              (def_state, self.unIdentifiedStateValuesStr))
    if debug: print("undefined state transitions:", self.undefined_transitions_hex)


  def ident_init_value(self, modFile:str, modName, rstSubStrings, clkSubstrings, debug=False):
    
    if self.fsmInitValue: 
      self.IDLE = {'name': None, 'value': self.fsmInitValue, 'id':None, 'flag':None, 'line':None, 'absValue': self.fsmInitValue}

    if self.fsmInitValue and self.fsmClk: return 
    
    if not self.modAst: 
      self.modAst, directives, self.modSeqAlwaysNodes = extractModuleAst(modName, modFile, clkSubstrings, debug)
    if not self.modAst: 
      print("\n--------------------------------------------------")
      print(f"WARNING: couldnt get clk or init value, {self.fsmClk}, {self.IDLE} for {self.fsmStateReg}, {modFile}")
      print(f"Skipping some sanitizers for this FSM. Add the fsm init value to config file to generate missing sanitizers for this FSM")
      print("--------------------------------------------------\n")
      return 

    fsm_state_signal = self.fsmFsmNode.attrib['name']
    init_state_value, init_state_type, self.fsmClk = ident_init_state_value(self.modSeqAlwaysNodes, fsm_state_signal\
                                            , rstSubStrings, self.modName, self.fsmStateReg, debug)
    init_state = None
    for s_id, s_data in self.identifiedStates.items():
      if init_state_type == 'Identifier': 
        if init_state_value == s_data["name"]:
          init_state = s_data;  break
      else: 
        if int(init_state_value) == s_data["absValue"]:
          init_state = s_data;  break
    assert init_state, f"couldnt find init state, {init_state_value}, {init_state_type}, {self.fsmLineNo}, {self.modName}, {self.identifiedStates}"

    self.IDLE = init_state
    if debug: print("initial state:", init_state_value, init_state)

  def ident_illeg_state_trans(self, debug=False):
    


    for src_state_hex in self.identifiedStateValuesHex: 
      for dst_state_hex in self.identifiedStateValuesHex: 
        if src_state_hex == dst_state_hex:
          continue
        if [src_state_hex, dst_state_hex] in self.identifiedTransitionsHex:
          continue
        self.illeg_transitions_hex.append([src_state_hex, dst_state_hex])
    if debug: print("illegal state transitions: ", self.illeg_transitions_hex)

def find_class_with_signal(ast, tar_class, tar_signals, debug=False):

  for child in ast.children():
    iden_sig = find_class_with_signal(child, tar_class, tar_signals, debug)
    if iden_sig == True:
      return True

  if ast.__class__.__name__ == tar_class:
    for tar_signal in tar_signals:
      if  tar_signal in ast.name:
        return True

  return False


def ident_init_state_value(seqAlwaysNodes, fsm_state_signal, rstSubStrings, modName, fsmStateReg, debug=False):
  init_state_value = None
  init_state_type = None

  ifBlocks = []
  for block, clk_signal, node_blocks in seqAlwaysNodes:
    ifBlocks += [[n, clk_signal] for n in node_blocks.ifstatement_blocks]

  ifBlocksWithRst = []
  for block, clk_signal in ifBlocks: 
    identFinder = NodeFinder()
    identFinder.visit(block.cond)
    ifCondIdentifierNames = [b.name for b in identFinder.Identifier_blocks]
    for identName in ifCondIdentifierNames: 
      if any((r in identName) for r in rstSubStrings): 
        ifBlocksWithRst.append([block, clk_signal]); break
  assert len(ifBlocksWithRst)>0, f'ident_init_state_value: did not find any if block with rst signal, {modName}, {fsmStateReg}'


  init_state_info = []
  for ifBlock, clk_signal in ifBlocksWithRst:
    subFinder = NodeFinder()
    subFinder.visit(ifBlock.true_statement)
    subBlocks = subFinder.NonblockingSubstitution_blocks
    subBlocks += subFinder.BlockingSubstitution_blocks

    for block in subBlocks:
      if find_class_with_signal(block.left, 'Identifier', [fsm_state_signal]):
        if block.right.var.__class__.__name__ == 'Identifier':
          init_state_value = block.right.var.name
          init_state_type = 'Identifier'
        elif block.right.var.__class__.__name__ == 'IntConst':
          init_state_value = convertVerilogValueToInt(block.right.var.value)
          print(init_state_value)
          init_state_type = 'value'
        else:
          print(f'ident_init_state_value: unknown var type, lineno {block.lineno}')
          exit()
        init_state_info.append([init_state_value, init_state_type, clk_signal, block.lineno])

  assert len(init_state_info) ==1, f'no or more than one  initial state value found in {modName}, {fsmStateReg}, {init_state_info}'
  
  print(init_state_info, '\n')
 
  return init_state_info[0][0:3]


def extract_fsm(fsm_entry:str, modList, rstSubStrings, clkSubstrings\
              , mode='jg', fsmInitValues=None, ignoreFsms=None, regList=None,debug=False):
  tree = et.parse(fsm_entry)
  root = tree.getroot()
  mods = []

  for i, child in enumerate(root):
    if child.tag == 'fsmdef':

      modFSM = next(( mod for mod in modList\
                      if (mod.modName == child.attrib["name"]) \
                        and (mod.modFileId == child.attrib["file"]) ), None)
      assert modFSM, f"couldnt find module for fsm, {child.attrib['name']}, {[m.modName for m in modList]}"

      fsminst_entry = child.findall("fsminst")
      instPathsFSM = [fe.attrib['name'] for fe in fsminst_entry]
      instPathsDesign = [v['path'] for k, v in modFSM.insts.items() if v['mid'] == modFSM.modId]
      assert all((i in instPathsDesign) for i in instPathsFSM), f"instance not found for fsm, {instPathsFSM}, {instPathsDesign}"
      instsFSM = {instId: instD for instId, instD in modFSM.insts.items()\
                      if instD['path'] in instPathsFSM}

      fsmShapeNodes = child.findall("fsmshape")
      modFSM.fsmFsmNodes = {i: [] for i in modFSM.insts.keys()}
      for fsn in fsmShapeNodes: 
        for instId in instsFSM.keys(): 
          modFSM.fsmFsmNodes[instId] += fsn.findall("fsmfsm")

  for mod in modList:
    for instId, fsmFsmNodesi in mod.fsmFsmNodes.items(): 
      for fsmFsmNode in fsmFsmNodesi: 

        fsmStateReg = f"{mod.insts[instId]['path']}.{fsmFsmNode.attrib['name']}"
        if fsmStateReg in ignoreFsms: continue
        if not fsmStateReg in regList: continue
        if regList: 
          fsmClk = regList[fsmStateReg][1].replace(mod.insts[instId]['path']+'.', '')
          fsmRst = regList[fsmStateReg][2] if len(regList[fsmStateReg]) > 2 else None
        else: 
          fsmClk = None
          fsmRst = None
        fsmInitValue = fsmInitValues.get(fsmStateReg, None)
        print(f'\n\nFSM file: {mod.modFile}\nFSM reg: {fsmStateReg}')
        fsm = FSMFSMNode(fsmFsmNode, mod.modName, mod.insts[instId], fsmStateReg, fsmInitValue, fsmClk, debug, fsmRst)
        mod.fsmList.append(fsm)
        fsm.parse_fsmfsm(debug)
        fsm.ident_undef_states(debug)
        fsm.ident_undef_state_trans(debug)
        fsm.ident_init_value(mod.modFile, mod.modName, rstSubStrings, clkSubstrings, debug)
        fsm.ident_illeg_state_trans(debug)

  return mods


def createFsmSanitizersMod(mod, fsmSanitizerTemplates, masterRstSignal, masterClkSignal\
                         , offset=0, debug=False):
  mod.fsmInstMetaData = {key: [] for key in fsmSanitizerTemplates.keys()}

  numSanitizers = 0
  for fsm in mod.fsmList:

    instp = fsm.fsmInst['path']
    fsmReset = fsm.fsmRst or masterRstSignal
    if fsm.IDLE: 
      fsmClk = f"{instp}.{fsm.fsmClk}"
    else: 
      fsmClk = masterClkSignal
      print(f"\n-------Rule 2 of FSM {fsm.fsmStateReg} in {fsm.modName} ignored--------\n")


    fsmSanitizerType = 'defUndefFsmTran'
    for ut in fsm.undefined_transitions_hex: 
      sanitizerId = f"{fsmSanitizerType}_{offset+numSanitizers:04d}"
      mod.fsmInstMetaData[fsmSanitizerType].append({'clk': fsmClk, 'mstRst': fsmReset\
                                                , 'stateReg': fsm.fsmStateReg\
                                                , 'defStateValue': ut[0], 'undefStateValues': ut[1]\
                                                , 'stype': fsmSanitizerType
                                                , 'id': sanitizerId
                                              })
      numSanitizers+=1
      
    if fsm.IDLE:
      idleStateValue = fsm.IDLE['absValue']
      fsmSanitizerType = 'fromUndefFsmTran'
      if fsm.unIdentifiedStateValuesStr != "":
        sanitizerId = f"{fsmSanitizerType}_{offset+numSanitizers:04d}"
        mod.fsmInstMetaData[fsmSanitizerType].append({'clk': fsmClk, 'mstRst': fsmReset\
                                                  , 'stateReg': fsm.fsmStateReg\
                                                  , 'undefStateValues': fsm.unIdentifiedStateValuesStr\
                                                  , 'idleStateValue': idleStateValue\
                                                  , 'stype': fsmSanitizerType
                                                  , 'id': sanitizerId
                                                })
        numSanitizers+=1
      
    fsmSanitizerType = 'reachDefFsmState'
    for def_state in fsm.identifiedStateValuesHex:
      sanitizerId = f"{fsmSanitizerType}_{offset+numSanitizers:04d}"
      mod.fsmInstMetaData[fsmSanitizerType].append({'clk': fsmClk, 'mstRst': fsmReset\
                                                , 'stateReg': fsm.fsmStateReg\
                                                , 'defStateValue': def_state\
                                                , 'id': sanitizerId
                                              })
      numSanitizers+=1
      
    fsmSanitizerType = 'reachDefFsmTran'
    for from_state, to_state in fsm.identifiedTransitionsHex:
      sanitizerId = f"{fsmSanitizerType}_{offset+numSanitizers:04d}"
      mod.fsmInstMetaData[fsmSanitizerType].append({'clk': fsmClk, 'mstRst': fsmReset\
                                                , 'stateReg': fsm.fsmStateReg\
                                                , 'defStateTranFrom': from_state\
                                                , 'defStateTranTo': to_state\
                                                , 'id': sanitizerId
                                              })
      numSanitizers+=1
      
    fsmSanitizerType = 'illFsmTran'
    for from_state, to_state in fsm.illeg_transitions_hex:
      sanitizerId = f"{fsmSanitizerType}_{offset+numSanitizers:04d}"
      mod.fsmInstMetaData[fsmSanitizerType].append({'clk': fsmClk, 'mstRst': fsmReset\
                                                , 'stateReg': fsm.fsmStateReg\
                                                , 'illTranFrom': from_state\
                                                , 'illTranTo': to_state\
                                                , 'stype': fsmSanitizerType
                                                , 'id': sanitizerId
                                              })
      numSanitizers+=1
      

  mod.fsmSanitizers = []
  for fsmSanitizerType, templateValuesList in mod.fsmInstMetaData.items():
    for templateValues in templateValuesList: 
      mod.fsmSanitizers.append(fsmSanitizerTemplates[fsmSanitizerType].substitute(**templateValues))

  return numSanitizers


def createFSMSanitizers(design, fsm_cg, fsmSanitizerTemplates, rstSubStrings, clkSubstrings\
                      , masterRstSignal, masterClkSignal, mode='jg', fsmInitValues=None\
                      , ignoreFsms=None, debug=False):

  assert exists(fsm_cg), f"file does not exists {fsm_cg}"
  fsm_entry = gzip.open(fsm_cg, 'rb')
  extract_fsm(fsm_entry, design.modList, rstSubStrings, clkSubstrings\
        , mode, fsmInitValues, ignoreFsms, design.regList, debug)
 
  sanitizerLines = []
  for mod in design.modList:
    sanitizerLines.append(f"\n// FSM sanitizers of {mod.modName} modules instances\n")
    design.numSanitizers += createFsmSanitizersMod(mod, fsmSanitizerTemplates\
                              , masterRstSignal, masterClkSignal, design.numSanitizers, debug)
    sanitizerLines += mod.fsmSanitizers 
  sanitizerLines.append(f"\n")

  return sanitizerLines


def main():


  CONFIG = getCONFIG(config, configType='file')
  simv_dir = CONFIG.CORE.pt['sim_dir_t'].substitute(tno=0) + '/simv.vdb/snps/coverage/db/'
  fsm_cg = join(simv_dir, 'shape/fsm.verilog.shape.xml')
  fsm_param = join(simv_dir, 'auxiliary/verilog.instance_parameters.txt')
  
  mod_info_dict = {}
  bench_dir = CONFIG.pt['benchmarks_dir']
  core_name = CONFIG.CORE.core_name
  if core_name == "sha256":
    mod_info_dict = {"sha256": [f"{bench_dir}/{core_name}/src/sha256.v", "rst"], \
                     "sha256_w_mem": [f"{bench_dir}/{core_name}/src/sha256_w_mem.v", "rst"]}
  
  elif CONFIG.CORE.core_name == "hmac":
    mod_info_dict = {"hmac": [f"{bench_dir}/{core_name}/src/hmac.sv", "rst_ni"], \
                     "sha256": [f"{bench_dir}/{core_name}/src/sha256.v", "rst"], \
                     "sha256_w_mem": [f"{bench_dir}/{core_name}/src/sha256_w_mem.v", "rst"]}

  elif CONFIG.CORE.core_name == "rsa":
    mod_info_dict = {"inverter": [f"{bench_dir}/{core_name}/src/inverter.v", "rst_n"], \
                     "mod_exp": [f"{bench_dir}/{core_name}/src/mod_exp.v", "rst_n"]}

  elif CONFIG.CORE.core_name == "dma":
    mod_info_dict = {"dma": [f"{bench_dir}/{core_name}/src/dma.sv", "rst_ni"]}

  elif CONFIG.CORE.core_name == "aes1":
    mod_info_dict = {"aes1_core": [f"{bench_dir}/{core_name}/src/aes1_core.v", "reset_n"], \
                     "aes_decipher_block": [f"{bench_dir}/{core_name}/src/aes1_decipher_block.v", "reset_n"], \
                     "aes_encipher_block": [f"{bench_dir}/{core_name}/src/aes1_encipher_block.v", "reset_n"], \
                     "aes_key_mem": [f"{bench_dir}/{core_name}/src/aes1_key_mem.v", "reset_n"]}

  elif CONFIG.CORE.core_name == "aes2":
    mod_info_dict = {"aes2_interface": [f"{bench_dir}/{core_name}/src/aes2_interface.v", "rst"], \
                     "gcm_aes_v0": [f"{bench_dir}/{core_name}/src/gcm_aes_v0.v", "rst"]}


  else:
    print("Unknown core: ", CONFIG.CORE.core_name)
    exit()

  createFSMSanitizers(fsm_cg, fsm_param, mod_info_dict)

if __name__ == '__main__':
  main()
