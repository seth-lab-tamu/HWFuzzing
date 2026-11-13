// Description: Access Control registers
//


module acct_wrapper #(
    parameter int unsigned AXI_ADDR_WIDTH = 64,
    parameter int unsigned AXI_DATA_WIDTH = 64,
    parameter int unsigned AXI_ID_WIDTH   = 10,
    parameter NB_SLAVE = 1,
    parameter NB_PERIPHERALS = 9
)(
           clk_i,
           rst_ni,
           reglk_ctrl_i,
           acct_ctrl_i,
           debug_mode_i,
           acc_ctrl_o,
           address, 
           en_acct, 
           we, 
           wdata, 
           rdata,
           we_flag,
		   rst_6
       );


    input  logic                   clk_i;
    input  logic                   rst_ni;
    input logic [7 :0]             reglk_ctrl_i; // register lock valuesA
    input logic                    acct_ctrl_i;
    input logic                    debug_mode_i;
    output logic [4*NB_PERIPHERALS-1 :0]   acc_ctrl_o; // Access control values
    input logic  we_flag;
    input logic [AXI_ADDR_WIDTH-1:0] address;
    input logic                      en_acct;
    input logic                      we;
    input logic [63:0] wdata;
    output logic [63:0] rdata;

    localparam AcCt_MEM_SIZE = NB_SLAVE*3 ;  // 32*3 bytes of access control for each slave interface

    input rst_6;

// internal signals

reg [AcCt_MEM_SIZE-1:0][31:0] acct_mem ; 
logic [15:0] reglk_ctrl ;  

logic                      en;

assign acc_ctrl_o = {acct_mem[3*0+2], acct_mem[3*0+1], acct_mem[3*0+0]|{8{we_flag}}}; 

assign reglk_ctrl = reglk_ctrl_i;

///////////////////////////////////////////////////////////////////////////
    assign en = en_acct && acct_ctrl_i; 

///////////////////////////////////////////////////////////////////////////
// Implement APB I/O map to PKT interface
// Write side
integer j;
always @(posedge clk_i)
    begin
        if(~(rst_ni && ~rst_6))
            begin
              for (j=0; j < AcCt_MEM_SIZE; j=j+1) begin
                acct_mem[j] <= 32'hffffffff; 
              end
            end
        else if(en && we)
            case(address[10:3])
                0:
                    acct_mem[00]  <= reglk_ctrl[5] ? acct_mem[00] : wdata;
                1:                                             
                    acct_mem[01]  <= reglk_ctrl[5] ? acct_mem[01] : wdata; 
                2:                                             
                    acct_mem[02]  <= reglk_ctrl[5] ? acct_mem[02] : wdata;
                // acct_mem valid indices are only 0,1,2. removing others to avoid JasperGold errors
                //3:                                              
                //    acct_mem[03]  <= reglk_ctrl[13] ? acct_mem[03] : wdata;
                //4:                                               
                //    acct_mem[04]  <= reglk_ctrl[13] ? acct_mem[04] : wdata;
                //5:                                               
                //    acct_mem[05]  <= reglk_ctrl[13] ? acct_mem[05] : wdata;
                //6:                                              
                //    acct_mem[06]  <= reglk_ctrl[1] ? acct_mem[06] : wdata;
                //7:                                              
                //    acct_mem[07]  <= reglk_ctrl[1] ? acct_mem[07] : wdata;
                //8:                                              
                //    acct_mem[08]  <= reglk_ctrl[1] ? acct_mem[08] : wdata;
                //9:                                              
                //    acct_mem[09]  <= reglk_ctrl[7] ? acct_mem[09] : wdata;
                default:
                    ;
            endcase
    end // always @ (posedge wb_clk_i)

//// Read side
always @(*)
    begin
      rdata = 64'b0; 
      if (en) begin
        case(address[10:3])
            0:
                rdata = reglk_ctrl[4] ? 'b0 : acct_mem[0]; 
            1:                                    
                rdata = reglk_ctrl[4] ? 'b0 : acct_mem[1];
            2:                                    
                rdata = reglk_ctrl[4] ? 'b0 : acct_mem[2];
            //3:                                    
            //    rdata = reglk_ctrl[2] ? 'b0 : acct_mem[3];
            //4:                                    
            //    rdata = reglk_ctrl[2] ? 'b0 : acct_mem[4];
            //5:                                    
            //    rdata = reglk_ctrl[2] ? 'b0 : acct_mem[5];
            //6:                                    
            //    rdata = reglk_ctrl[0] ? 'b0 : acct_mem[6];
            //7:                                    
            //    rdata = reglk_ctrl[0] ? 'b0 : acct_mem[7];
            //8:                                    
            //    rdata = reglk_ctrl[0] ? 'b0 : acct_mem[8];
            //9:                                    
            //    rdata = reglk_ctrl[6] ? 'b0 : acct_mem[9];
            default:
                rdata = 32'b0;
        endcase
      end // if
    end // always @ (*)


endmodule
