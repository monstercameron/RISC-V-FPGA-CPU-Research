"""Built-in, bounded C lessons and independent expected answers.
SPDX-License-Identifier: MIT
"""
from program_inputs import expected_output, SCHEMAS

PROGRAMS = {
    'add': {
        'title': '1 + 1', 'source': 'sim/cpu/add_one.c', 'level': 1, 'speed': 4,
        'summary': 'Start with one addition: load two ones, add them, and save 2.',
        'concepts': ['Registers', 'ADD', 'Store to RAM'],
        'watch': ['Watch x10 and x11 supply the two inputs to the ALU.',
                  'The answer reaches a register before it reaches the output mailbox.'],
        'question': 'At clock 28 the register contains 2. Why is the output still waiting?',
        'answer': 'ADD only writes a register. A later store writes 2 to RAM at clock 41.',
        'outputs': [('1 + 1', 'signed')], 'stops': ['load', 'output'],
    },
    'branch': {
        'title': 'Make a decision', 'source': 'sim/cpu/programs/decisions.c', 'level': 2, 'speed': 60,
        'summary': 'Test -7 and 4. Negate a negative input; otherwise add 10.',
        'concepts': ['Signed comparison', 'Conditional branch', 'Two paths'],
        'watch': ['Compare taken and not-taken executions of the same signed branch.',
                  'Follow the next address as the CPU chooses which arithmetic to execute.'],
        'question': 'Why does the same branch instruction choose different paths?',
        'answer': 'Its register input changes from -7 to 4. The comparison result determines the next PC.',
        'outputs': [('Negative path: -(-7)', 'signed'), ('Other path: 4 + 10', 'signed')],
        'stops': ['decisionTaken', 'decisionNotTaken', 'output'],
    },
    'loop': {
        'title': 'Count and accumulate', 'source': 'sim/cpu/programs/counting.c', 'level': 3, 'speed': 60,
        'summary': 'Add the integers from 1 through 10, keeping a running total.',
        'concepts': ['Counter', 'Accumulator', 'Backward branch'],
        'watch': ['A taken backward branch sends the CPU around the loop again.',
                  'Compare that branch with its final not-taken execution.'],
        'question': 'How can a short sequence of instructions perform ten additions?',
        'answer': 'The loop branch reuses the same instructions while the counter and sum change.',
        'outputs': [('Sum: 1 through 10', 'signed'), ('Iterations', 'signed')],
        'stops': ['backward', 'loopExit', 'output'],
    },
    'array': {
        'title': 'Read an array', 'source': 'sim/cpu/programs/arrays.c', 'level': 4, 'speed': 60,
        'summary': 'Scan [8, -3, 12, 5, -2] and find its sum, minimum, and maximum.',
        'concepts': ['Addresses', '64-bit loads', 'Signed values'],
        'watch': ['Each array element occupies eight bytes; watch the data address change.',
                  'A load waits for RAM before the destination register changes.'],
        'question': 'How does RAM store -3 if its bits are only zeros and ones?',
        'answer': 'It uses 64-bit two’s complement. The same bits display as 0xfffffffffffffffd in hexadecimal or -3 as signed decimal.',
        'outputs': [('Sum', 'signed'), ('Minimum', 'signed'), ('Maximum', 'signed')],
        'stops': ['load', 'nextLoad', 'backward', 'output'],
    },
    'calls': {
        'title': 'Functions and the stack', 'source': 'sim/cpu/programs/calls.c', 'level': 5, 'speed': 60,
        'summary': 'Compute 5 + 4 + 3 + 2 + 1 using recursive function calls.',
        'concepts': ['Call / return', 'Stack pointer', 'Saved values'],
        'watch': ['x1 (ra) holds a return address; x2 (sp) tracks stack space.',
                  'Each call saves state in RAM, then restores it while the recursion unwinds.'],
        'question': 'Why save a return address in RAM when x1 already holds one?',
        'answer': 'The next call overwrites x1. Saving the previous address on the stack lets each caller resume at the right place.',
        'outputs': [('Triangular number: T(5)', 'signed')],
        'stops': ['stackWrite', 'call', 'recursiveCall', 'return', 'output'],
    },
    'sort': {
        'title': 'Sort six numbers', 'source': 'sim/cpu/programs/sorting.c', 'level': 6, 'speed': 60,
        'summary': 'Use insertion sort to rearrange [9, 3, 7, 1, 5, 2] into ascending order.',
        'concepts': ['Nested loops', 'Compare and shift', 'Array stores'],
        'watch': ['The inner loop moves larger elements one position to the right.',
                  'Data writes change the working array before the final output is published.'],
        'question': 'Why do array writes occur long before the output rows fill?',
        'answer': 'Sorting modifies its working array first. A separate final loop copies the sorted numbers into the output mailbox.',
        'outputs': [(f'Sorted [{i}]', 'signed') for i in range(6)],
        'stops': ['load', 'dataWrite', 'backward', 'output'],
    },
    'demo': {
        'title': 'Sort, Fibonacci & CRC32', 'source': 'sim/cpu/c_demo.c', 'level': 7, 'speed': 6000,
        'summary': 'Combine sorting, a Fibonacci sequence, and a byte-by-byte checksum.',
        'concepts': ['Multiple algorithms', 'Shifts and XOR', 'Longer execution'],
        'watch': ['Use the chapter menu to move between sorting, Fibonacci, and CRC32.',
                  'CRC32 uses shifts and XOR; the CPU has no dedicated checksum instruction.'],
        'question': 'Does faster playback make the simulated CPU finish in fewer clocks?',
        'answer': 'No. Playback only changes how quickly you view the already captured clocks. Run simulation performs a new execution.',
        'outputs': list(zip(['Completion marker', 'Status', 'Sum', 'Minimum', 'Maximum',
                             'Fibonacci(40)', 'CRC32 · 344 bytes', 'Sorted fingerprint'],
                            ['marker', 'signed', 'signed', 'signed', 'signed', 'signed', 'hex', 'hex'])),
        'stops': [],
    },
}


def public_catalog():
    return [dict(id=key, inputSchema=SCHEMAS[key], **{k: spec[k] for k in
            ('title', 'level', 'summary', 'concepts', 'watch', 'question', 'answer', 'speed')})
            for key, spec in PROGRAMS.items()]
