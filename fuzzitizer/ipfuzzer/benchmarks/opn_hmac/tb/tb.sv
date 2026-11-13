module opn_hmac_tb #(
      parameter int unsigned MAX_CYCLES = 2000
    , parameter WAVE_ENABLE = 0
    , parameter CLOCK_PERIOD = 2ns
  ) ();

  localparam int unsigned AXI_ADDR_WIDTH = 64;
  localparam int unsigned AXI_DATA_WIDTH = 64;
  localparam int unsigned AXI_ID_WIDTH = 1;

  // variables
  logic clk_i, rst_ni;
  logic [0:0] en_acct;
  logic [0:0] we;
  logic [63:0] address;
  logic [63:0] wdata;
  logic [63:0] rdata;
  logic [7:0] reglk_ctrl_i;
  logic [0:0] acct_ctrl_i;
  logic [0:0] debug_mode_i;
  logic [0:0] rst_4;


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
    en_acct = {1{1'b0}};
    we = {1{1'b0}};
    address = {64{1'b0}};
    wdata = {64{1'b0}};
    reglk_ctrl_i = {8{1'b0}};
    acct_ctrl_i = {1{1'b0}};
    debug_mode_i = {1{1'b0}};
    rst_4 = {1{1'b0}};

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
      $fscanf(fp, "%h,%h,%h,%h,%h,%h,%h,%h", en_acct, we, address, wdata, reglk_ctrl_i, acct_ctrl_i, debug_mode_i, rst_4);
      $display("time=%8d, Read en_acct=%h, we=%h, address=%h, wdata=%h, reglk_ctrl_i=%h, acct_ctrl_i=%h, debug_mode_i=%h, rst_4=%h", $time, en_acct, we, address, wdata, reglk_ctrl_i, acct_ctrl_i, debug_mode_i, rst_4);
      @(negedge clk_i);
    end
    $fclose(fp); 
    $display("INFO: Finished reading data from %s", input_file);
  end
  

  // Instantiate the peripheral
  hmac_wrapper #(
    .AXI_ADDR_WIDTH(AXI_ADDR_WIDTH),
    .AXI_DATA_WIDTH(AXI_DATA_WIDTH),
    .AXI_ID_WIDTH(AXI_ID_WIDTH)
  ) perif_u (
      .clk_i (clk_i)
    , .rst_ni (rst_ni)
    , .en_acct ( en_acct )
    , .we ( we )
    , .address ( address )
    , .wdata ( wdata )
    , .rdata ( rdata )
    , .reglk_ctrl_i ( reglk_ctrl_i )
    , .acct_ctrl_i ( acct_ctrl_i )
    , .debug_mode_i ( debug_mode_i )
    , .rst_4 ( rst_4 )
  );

endmodule
