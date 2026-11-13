
import os
import random
import uuid

import fuzz_utils


def gen_multi_prog(del_repo, mode, inst_output_path, num_progs,
                   fuzzer_input_file_t, input_format_info, num_clocks_in_input,
                   mutation_prob, trash_dir='/tmp/'):
    if mode not in ['random', 'fuzz']:
        print("Unknown mode received", mode)
        raise SystemExit

    generated_test_files = []

    if del_repo:
        fuzz_utils.delete_dir(
            inst_output_path,
            True,
            'move',
            f"{trash_dir}/prog_gen_{uuid.uuid1()}",
        )

    for prog_no in range(num_progs):
        file_name = fuzzer_input_file_t.substitute(fno=str(prog_no))
        file_fullpath = os.path.join(inst_output_path, file_name)
        generated_test_files.append(file_fullpath)

        with open(file_fullpath, 'w') as file_p:
            gen_random_perif_input(
                file_p,
                num_clocks_in_input,
                input_format_info,
                mutation_prob,
            )

    return generated_test_files


def gen_random_perif_input(file_p, num_clocks_in_input, input_format_info, mutation_prob):

    prev_values = {i['name']:None for i in input_format_info}
    for clk_i in range(num_clocks_in_input):
        line = ""
        assert len(input_format_info) > 0, f"no input format data provided, {input_format_info}"
        for input_i in input_format_info:
            if not (input_i['type'] in ['gen']):
                continue
            prev_value = prev_values[input_i['name']]
            if prev_value == None:
                value = random.randint(0, 2**input_i['nbits']-1)
                prev_values[input_i['name']] = value
            else:
                if ('rst' in input_i['name']):
                    if ((input_i['edge']=='posedge') and prev_value)\
                         or ((input_i['edge']=='negedge') and (prev_value==0)):
                        mutation_prob_local = 80
                    else:
                        mutation_prob_local = mutation_prob * 0.1
                else:
                    mutation_prob_local = mutation_prob

                if (random.randint(0,9999) > (mutation_prob_local*100)):
                    value = prev_value
                else:
                    value = random.randint(0, 2**input_i['nbits']-1)
                    prev_values[input_i['name']] = value
            line = line + hex(value)[2:] + ","

        file_p.write(f"{line[:-1]}\n")
