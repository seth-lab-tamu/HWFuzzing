module opn_dbg_tb #(
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
  logic [7:0] slave_be_i;
  logic [3:0] priv_lvl_i;
  logic [255:0] jtag_hash_i;
  logic [255:0] ikey_hash_i;
  logic [255:0] okey_hash_i;
  logic [0:0] we_flag_4_i;
  logic [0:0] tck_i;
  logic [0:0] tms_i;
  logic [0:0] td_i;
  logic [0:0] trst_ni;
  logic [0:0] td_o;
  logic [0:0] tdo_oe_o;


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
    slave_be_i = {8{1'b0}};
    priv_lvl_i = {4{1'b0}};
    jtag_hash_i = {256{1'b0}};
    ikey_hash_i = {256{1'b0}};
    okey_hash_i = {256{1'b0}};
    we_flag_4_i = {1{1'b0}};
    tck_i = {1{1'b0}};
    tms_i = {1{1'b0}};
    td_i = {1{1'b0}};
    trst_ni = {1{1'b0}};

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
      $fscanf(fp, "%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h,%h", en_acct, we, address, wdata, slave_be_i, priv_lvl_i, jtag_hash_i, ikey_hash_i, okey_hash_i, we_flag_4_i, tck_i, tms_i, td_i, trst_ni);
      $display("time=%8d, Read en_acct=%h, we=%h, address=%h, wdata=%h, slave_be_i=%h, priv_lvl_i=%h, jtag_hash_i=%h, ikey_hash_i=%h, okey_hash_i=%h, we_flag_4_i=%h, tck_i=%h, tms_i=%h, td_i=%h, trst_ni=%h", $time, en_acct, we, address, wdata, slave_be_i, priv_lvl_i, jtag_hash_i, ikey_hash_i, okey_hash_i, we_flag_4_i, tck_i, tms_i, td_i, trst_ni);
      @(negedge clk_i);
    end
    $fclose(fp); 
    $display("INFO: Finished reading data from %s", input_file);
  end
  

  // Instantiate the peripheral
  dbg_wrapper #(
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
    , .slave_be_i ( slave_be_i )
    , .priv_lvl_i ( priv_lvl_i )
    , .jtag_hash_i ( jtag_hash_i )
    , .ikey_hash_i ( ikey_hash_i )
    , .okey_hash_i ( okey_hash_i )
    , .we_flag_4_i ( we_flag_4_i )
    , .tck_i ( tck_i )
    , .tms_i ( tms_i )
    , .td_i ( td_i )
    , .trst_ni ( trst_ni )
    , .td_o ( td_o )
    , .tdo_oe_o ( tdo_oe_o )
  );

endmodule
