module cal_csrng_tb #(
      parameter int unsigned MAX_CYCLES = 2000
    , parameter WAVE_ENABLE = 0
    , parameter CLOCK_PERIOD = 2ns
  ) ();

  localparam int unsigned AHBAddrWidth = 12;
  localparam int unsigned AHBDataWidth = 64;

  // variables
  logic clk_i, rst_ni;
  logic [0:0] cs;
  logic [0:0] we;
  logic [11:0] address;
  logic [31:0] write_data;
  logic [31:0] read_data;
  logic [0:0] err;
  logic [0:0] hold;
  logic [7:0] otp_en_csrng_sw_app_read_i;
  logic [3:0] lc_hw_debug_en_i;
  logic [0:0] entropy_src_hw_if_o;
  logic [385:0] entropy_src_hw_if_i;
  logic [0:0] cs_aes_halt_i;
  logic [0:0] cs_aes_halt_o;
  logic [67:0] csrng_cmd_i;
  logic [265:0] csrng_cmd_o;
  logic [3:0] alert_tx_o;
  logic [7:0] alert_rx_i;
  logic [0:0] intr_cs_cmd_req_done_o;
  logic [0:0] intr_cs_entropy_req_o;
  logic [0:0] intr_cs_hw_inst_exc_o;
  logic [0:0] intr_cs_fatal_err_o;


  // collecting waveform
  initial begin
    if (WAVE_ENABLE == 1) begin
      $display("\nINFO: Dumping waveform\n");
      $vcdpluson;
      //$vcdplusmemon;
    end
  end
  

  // Clock and reset logic
  longint unsigned cycles;
  initial begin
    $display("\nINFO: Starting simulation\n");
    clk_i = 1'b0;
    rst_ni = 1'b0;
    repeat(8)
      #(CLOCK_PERIOD/2) clk_i = ~clk_i;
    rst_ni = 1'b1;
    cycles = 0; 
    forever begin
      #(CLOCK_PERIOD/2) clk_i = 1'b1;
      #(CLOCK_PERIOD/2) clk_i = 1'b0;

      if (cycles >= MAX_CYCLES) begin 
        $display("\nINFO: Max cycles reached %d\n\n", MAX_CYCLES);
        $finish(); 
      end
      cycles++;
    end
  end


  // read input data file and drive the inputs to the peripheral
  int fp; 
  string input_file = "input.csv";
  initial begin
    // initialize variables
    cs = {1{1'b0}};
    we = {1{1'b0}};
    address = {12{1'b0}};
    write_data = {32{1'b0}};
    otp_en_csrng_sw_app_read_i = {8{1'b0}};
    lc_hw_debug_en_i = {4{1'b0}};
    entropy_src_hw_if_i = {386{1'b0}};
    cs_aes_halt_i = {1{1'b0}};
    csrng_cmd_i = {68{1'b0}};
    alert_rx_i = {8{1'b0}};

    wait(~rst_ni);
    wait(rst_ni);
     
    @(posedge clk_i);
    @(negedge clk_i);

    // open file
    fp = $fopen(input_file, "r"); 
    if (fp == 0)
      $display("ERROR: Could not open file '%s' for reading", input_file);
    else 
      $display("INFO: Reading data from '%s'", input_file);

    // drive data from file
    while (!$feof(fp)) begin
      $fscanf(fp, "%h,%h,%h,%h,%h,%h,%h,%h,%h,%h", cs, we, address, write_data, otp_en_csrng_sw_app_read_i, lc_hw_debug_en_i, entropy_src_hw_if_i, cs_aes_halt_i, csrng_cmd_i, alert_rx_i);
      $display("time=%8d, Read cs=%h, we=%h, address=%h, write_data=%h, otp_en_csrng_sw_app_read_i=%h, lc_hw_debug_en_i=%h, entropy_src_hw_if_i=%h, cs_aes_halt_i=%h, csrng_cmd_i=%h, alert_rx_i=%h", $time, cs, we, address, write_data, otp_en_csrng_sw_app_read_i, lc_hw_debug_en_i, entropy_src_hw_if_i, cs_aes_halt_i, csrng_cmd_i, alert_rx_i);
      @(negedge clk_i);
    end
    $fclose(fp); 
    $display("INFO: Finished reading data from %s", input_file);
  end
  

  // Instantiate the peripheral
  csrng #(
    .AHBAddrWidth(AHBAddrWidth),
    .AHBDataWidth(AHBDataWidth)
  ) perif_u (
      .clk_i (clk_i)
    , .rst_ni (rst_ni)
    , .cs ( cs )
    , .we ( we )
    , .address ( address )
    , .write_data ( write_data )
    , .read_data ( read_data )
    , .err ( err )
    , .hold ( hold )
    , .otp_en_csrng_sw_app_read_i ( caliptra_prim_mubi_pkg::mubi8_t'(otp_en_csrng_sw_app_read_i) )
    , .lc_hw_debug_en_i ( lc_ctrl_pkg::lc_tx_t'(lc_hw_debug_en_i) )
    , .entropy_src_hw_if_o ( entropy_src_hw_if_o )
    , .entropy_src_hw_if_i ( entropy_src_hw_if_i )
    , .cs_aes_halt_i ( cs_aes_halt_i )
    , .cs_aes_halt_o ( cs_aes_halt_o )
    , .csrng_cmd_i ( csrng_cmd_i )
    , .csrng_cmd_o ( csrng_cmd_o )
    , .alert_tx_o ( alert_tx_o )
    , .alert_rx_i ( alert_rx_i )
    , .intr_cs_cmd_req_done_o ( intr_cs_cmd_req_done_o )
    , .intr_cs_entropy_req_o ( intr_cs_entropy_req_o )
    , .intr_cs_hw_inst_exc_o ( intr_cs_hw_inst_exc_o )
    , .intr_cs_fatal_err_o ( intr_cs_fatal_err_o )
  );

endmodule
