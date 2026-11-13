import os
from string import Template


### reset sanitizer templates
InRstDomTemplate = Template("typedef logic [$$bits(${sig})-1:0] t_${id};"\
                          + "\nproperty p_${id};"\
                          + "\n@(posedge ${clk}) (${rstType}${rst})"\
                          + " |=> ~|(t_${id}'({>>{${sig}}}) === {$$bits(${sig}){1'bx}});"\
                          + "\nendproperty;"\
                          + '\na_${id}: assert property(p_${id}) else $$display("ERROR, Sanitizer:${stype}, time=%4d, ${sig}=%h", $$time, $$sampled(t_${id}\'({>>{${sig}}})));\n')
rstSanitizerTemplates = {'InRstDom': InRstDomTemplate}


### fsm sanitizer templates
prefix = "property p_${id};\n@(posedge ${clk}) disable iff (${mstRst})"
assertPostfix = "\nendproperty;"
assertPostfix +='\na_${id}: assert property(p_${id}) else $$display("ERROR, Sanitizer:${stype}, time=%4d, ${stateReg}=%h, ${stateReg}_past=%h", $$time, $$sampled(${stateReg}), $$past(${stateReg}));\n'
stateCoverPostfix = "\nendproperty;"
stateCoverPostfix += "\nbit c_${id}_reported = 1'b0;"
stateCoverPostfix += '\na_${id}: cover property(p_${id}) begin\n  if (!c_${id}_reported) begin\n    $$display("COVER, Sanitizer:reachDefFsmState, id=${id}, time=%4d, state_reg=${stateReg}, state=${defStateValue}", $$time);\n    c_${id}_reported = 1\'b1;\n  end\nend\n'
transitionCoverPostfix = "\nendproperty;"
transitionCoverPostfix += "\nbit c_${id}_reported = 1'b0;"
transitionCoverPostfix += '\na_${id}: cover property(p_${id}) begin\n  if (!c_${id}_reported) begin\n    $$display("COVER, Sanitizer:reachDefFsmTran, id=${id}, time=%4d, state_reg=${stateReg}, from=${defStateTranFrom}, to=${defStateTranTo}", $$time);\n    c_${id}_reported = 1\'b1;\n  end\nend\n'

defUndefFsmTranTemplate = Template(prefix\
                                + " (${stateReg} == ${defStateValue})"\
                                + " |=> !(${stateReg} inside {${undefStateValues}});"\
                                + assertPostfix)

fromUndefFsmTranTemplate = Template(prefix\
                                + " (${stateReg} inside {${undefStateValues}})"\
                                + " |=> (${stateReg} == ${idleStateValue});"\
                                + assertPostfix)

reachDefFsmStateTemplate = Template(prefix\
                                + " (${stateReg} == ${defStateValue});"\
                                + stateCoverPostfix)

reachDefFsmTranTemplate = Template(prefix\
                                + " (!$$past(${mstRst}))"\
                                + " && ($$past(${stateReg}) == ${defStateTranFrom})"\
                                + " && (${stateReg} == ${defStateTranTo});"
                                + transitionCoverPostfix)

illFsmTranTemplate = Template(prefix\
                                + " (${stateReg} == ${illTranFrom})"\
                                + " |=> !(${stateReg} == ${illTranTo});"
                                + assertPostfix)


fsmSanitizerTemplates = {'defUndefFsmTran': defUndefFsmTranTemplate\
                       , 'fromUndefFsmTran': fromUndefFsmTranTemplate\
                       , 'reachDefFsmState': reachDefFsmStateTemplate\
                       , 'reachDefFsmTran': reachDefFsmTranTemplate\
                       , 'illFsmTran': illFsmTranTemplate}



### zero sanitizer templates

clrOnDbgTemplate = Template("typedef logic [$$bits(${sig})-1:0] t_${id};"\
                          + "\nproperty p_${id};"\
                          + "\n@(posedge ${clk}) $$rose(${debugEn})"\
                          + " |=> ~|(t_${id}'({>>{${sig}}}));"\
                          + "\nendproperty;"\
                          + '\na_${id}: assert property(p_${id}) else $$display("ERROR, Sanitizer:${stype}, time=%4d, ${sig}=%h", $$time, $$sampled(t_${id}\'({>>{${sig}}})));\n')

OneTimeZeroTemplate = Template("typedef logic [$$bits(${clearSig})-1:0] t_${id}_clear;"\
                          + "\nproperty p_${id};"\
                          + "\n@(posedge ${clk}) (${valid}) && (${targetWord} != '0) && (${targetWord} == ${outputData})"\
                          + " |=> (~|(t_${id}_clear'({>>{${clearSig}}})));"\
                          + "\nendproperty;"\
                          + '\na_${id}: assert property(p_${id}) else $$display("ERROR, Sanitizer:${stype}, time=%4d, ${targetWord}=%h, ${outputData}=%h, ${clearSig}=%h", $$time, $$sampled(${targetWord}), $$sampled(${outputData}), $$sampled(t_${id}_clear\'({>>{${clearSig}}})));\n')

zeroSanitizerTemplates = {'clrOnDbg': clrOnDbgTemplate\
                        , 'OneTimeZero': OneTimeZeroTemplate}
