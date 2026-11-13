
import logging as lg
import os
import random


def data_hex_to_bin(data_hex, num_bits):
    data_bin = bin(int(data_hex, 16))[2:]
    data_bin = data_bin.zfill(num_bits)
    assert len(data_bin) > num_bits - 1, (
        f"hex to bin conversion failed, {data_hex}, {num_bits}, {data_bin}"
    )
    return data_bin


def data_bin_to_hex(data_bin, num_bits):
    data_hex = hex(int(data_bin, 2))[2:]
    return data_hex


def select_mutation_indices(num_bits, num_bits_to_mut):
    available_indices = list(range(num_bits))
    if len(available_indices) < num_bits_to_mut:
        return available_indices

    start_index = random.randint(0, len(available_indices) - 1)
    available_indices = available_indices + available_indices
    return available_indices[start_index:start_index + num_bits_to_mut]


def bitflip(mut, num_bits_to_mut):
    m_index = select_mutation_indices(len(mut), num_bits_to_mut)
    mut_list = list(mut)
    for index in m_index:
        mut_list[index] = "0" if mut_list[index] == "1" else "1"
    return "".join(mut_list)


def arith(mut, num_bytes_to_mut):
    if num_bytes_to_mut not in [1, 2]:
        print("Error. invalid num of bytes to arith function")
        exit()

    m_index = select_mutation_indices(len(mut), 8 * num_bytes_to_mut)
    if len(m_index) == 0:
        return mut

    mut_list = list(mut)
    mut_byte = "".join(mut_list[index] for index in m_index)
    mut_byte = int(mut_byte, 2)
    mut_byte += random.randint(-35, 35)

    if num_bytes_to_mut == 1:
        mut_byte = (mut_byte + 2**8 - 1) if mut_byte < 0 else mut_byte
        mut_byte = "{0:08b}".format(mut_byte)
    elif num_bytes_to_mut == 2:
        mut_byte = (mut_byte + 2**16 - 1) if mut_byte < 0 else mut_byte
        mut_byte = "{0:016b}".format(mut_byte)

    for byte_num, index in enumerate(m_index):
        mut_list[index] = mut_byte[-len(m_index) + byte_num]
    return "".join(mut_list)


def bitflip_1(mut):
    return bitflip(mut, 1)


def bitflip_2(mut):
    return bitflip(mut, 2)


def bitflip_4(mut):
    return bitflip(mut, 4)


def byte_flip(mut):
    return bitflip(mut, 8)


def byte_flip_16(mut):
    return bitflip(mut, 16)


def arith_8(mut):
    return arith(mut, 1)


def arith_16(mut):
    return arith(mut, 2)


def random_8(mut):
    return randomize_bits(mut, 8)


def randomize_bits(mut, num_bits_to_mut):
    m_index = select_mutation_indices(len(mut), num_bits_to_mut)
    mut_list = list(mut)
    for index in m_index:
        mut_list[index] = str(random.randint(0, 1))
    return "".join(mut_list)


def mut_data(data_to_mut, num_bits, mutation_prob, val_muts):
    if random.randint(0, 9999) > (mutation_prob * 100):
        return data_to_mut

    data_bin_rev = data_hex_to_bin(data_to_mut, num_bits)[::-1]
    mutation_type = random.choice(val_muts)
    if mutation_type == 0:
        mutated = bitflip_1(data_bin_rev)
    elif mutation_type == 1:
        mutated = bitflip_2(data_bin_rev)
    elif mutation_type == 2:
        mutated = bitflip_4(data_bin_rev)
    elif mutation_type == 3:
        mutated = arith_8(data_bin_rev)
    elif mutation_type == 4:
        mutated = arith_16(data_bin_rev)
    elif mutation_type == 5:
        mutated = random_8(data_bin_rev)
    elif mutation_type == 6:
        mutated = byte_flip(data_bin_rev)
    elif mutation_type == 7:
        mutated = byte_flip_16(data_bin_rev)
    else:
        print("Error: Incorrect Mutation")

    return data_bin_to_hex(mutated[::-1], num_bits)


def mutate_inputs(
    ip_file_in,
    ip_file_out,
    mutation_prob,
    val_muts,
    input_format_info,
):
    lg.debug("generating", os.path.basename(ip_file_out), "from", os.path.basename(ip_file_in))

    with open(ip_file_in, "r") as input_file:
        input_lines = input_file.readlines()

    generated_inputs = [item for item in input_format_info if item["type"] == "gen"]
    with open(ip_file_out, "w") as output_file:
        for line in input_lines:
            line_data = line.strip().split(",")
            new_values = []
            for data, input_info in zip(line_data, generated_inputs):
                if "rst" in input_info["name"]:
                    reset_enabled = (
                        (input_info["edge"] == "posedge" and int(data))
                        or (input_info["edge"] == "negedge" and int(data) == 0)
                    )
                    if reset_enabled:
                        mutation_prob_local = 80
                        if random.randint(0, 9999) > (mutation_prob_local * 100):
                            value = data
                        else:
                            value = "0" if data == "1" else "1"
                        new_values.append(value)
                        continue
                    mutation_prob_local = mutation_prob * 0.1
                else:
                    mutation_prob_local = mutation_prob

                new_values.append(
                    mut_data(
                        data,
                        input_info["nbits"],
                        mutation_prob_local,
                        val_muts,
                    )
                )
            output_file.write(",".join(new_values) + "\n")
