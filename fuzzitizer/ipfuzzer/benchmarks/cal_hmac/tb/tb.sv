module cal_hmac_tb #(
      parameter int unsigned MAX_CYCLES = 2000
    , parameter WAVE_ENABLE = 0
    , parameter CLOCK_PERIOD = 2ns
  ) ();

  localparam int unsigned AHB_ADDR_WIDTH = 12;
  localparam int unsigned AHB_DATA_WIDTH = 64;

  // variables
  logic clk_i, rst_ni;
  logic [0:0] cs;
  logic [0:0] we;
  logic [11:0] address;
  logic [31:0] write_data;
  logic [31:0] read_data;
  logic [0:0] cptra_pwrgood;
  logic [17:0] kv_read;
  logic [46:0] kv_write;
  logic [67:0] kv_rd_resp;
  logic [0:0] kv_wr_resp;
  logic [0:0] error_intr;
  logic [0:0] notif_intr;
  logic [0:0] debugUnlock_or_scan_mode_switch;


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
    cptra_pwrgood = {1{1'b0}};
    kv_rd_resp = {68{1'b0}};
    kv_wr_resp = {1{1'b0}};
    debugUnlock_or_scan_mode_switch = {1{1'b0}};

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
      $fscanf(fp, "%h,%h,%h,%h,%h,%h,%h,%h", cs, we, address, write_data, cptra_pwrgood, kv_rd_resp, kv_wr_resp, debugUnlock_or_scan_mode_switch);
      $display("time=%8d, Read cs=%h, we=%h, address=%h, write_data=%h, cptra_pwrgood=%h, kv_rd_resp=%h, kv_wr_resp=%h, debugUnlock_or_scan_mode_switch=%h", $time, cs, we, address, write_data, cptra_pwrgood, kv_rd_resp, kv_wr_resp, debugUnlock_or_scan_mode_switch);
      @(negedge clk_i);
    end
    $fclose(fp); 
    $display("INFO: Finished reading data from %s", input_file);
  end
  

  // Instantiate the peripheral
  hmac_ctrl #(
    .AHB_ADDR_WIDTH(AHB_ADDR_WIDTH),
    .AHB_DATA_WIDTH(AHB_DATA_WIDTH)
  ) perif_u (
      .clk (clk_i)
    , .reset_n (rst_ni)
    , .cs ( cs )
    , .we ( we )
    , .address ( address )
    , .write_data ( write_data )
    , .read_data ( read_data )
    , .cptra_pwrgood ( cptra_pwrgood )
    , .kv_read ( kv_read )
    , .kv_write ( kv_write )
    , .kv_rd_resp ( kv_rd_resp )
    , .kv_wr_resp ( kv_wr_resp )
    , .error_intr ( error_intr )
    , .notif_intr ( notif_intr )
    , .debugUnlock_or_scan_mode_switch ( debugUnlock_or_scan_mode_switch )
  );

endmodule
