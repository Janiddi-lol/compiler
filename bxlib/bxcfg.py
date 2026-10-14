# --------------------------------------------------------------------
from __future__ import annotations

from dataclasses import dataclass, field

from .bxtac import JUMPS, TAC


# ====================================================================
# Control-flow graph simplification

_TERMINATORS = {"jmp", "ret"}
_INVERSE_JUMP = {
    "jz": "jnz",
    "jnz": "jz",
    "jl": "jnl",
    "jnl": "jl",
    "jle": "jnle",
    "jnle": "jle",
}


@dataclass(eq=False)
class _Block:
    """A basic block, including every label that aliases its entry."""

    labels: list[str] = field(default_factory=list)
    body: list[TAC] = field(default_factory=list)


def _fresh_label(body: list[TAC]):
    used = {
        str(instruction.arguments[0])
        for instruction in body
        if instruction.opcode == "label"
    }
    number = 0

    def fresh() -> str:
        nonlocal number
        while True:
            label = f"%.Lcfg{number}"
            number += 1
            if label not in used:
                used.add(label)
                return label

    return fresh


def _make_blocks(body: list[TAC]) -> list[_Block]:
    """Normalize TAC and split it into basic blocks."""

    if not body:
        return []

    fresh = _fresh_label(body)
    normalized: list[TAC] = []
    if body[0].opcode != "label":
        normalized.append(TAC("label", [fresh()]))

    for instruction in body:
        if (
            normalized
            and instruction.opcode != "label"
            and (
                normalized[-1].opcode in _TERMINATORS
                or (
                    normalized[-1].opcode in JUMPS
                    and instruction.opcode not in JUMPS
                    and instruction.opcode not in _TERMINATORS
                )
            )
        ):
            normalized.append(TAC("label", [fresh()]))
        normalized.append(instruction)

    blocks: list[_Block] = []
    current: _Block | None = None
    for instruction in normalized:
        if instruction.opcode == "label":
            label = str(instruction.arguments[0])
            if current is None:
                current = _Block([label])
            elif current.body:
                blocks.append(current)
                current = _Block([label])
            else:
                current.labels.append(label)
            continue

        if current is None:
            current = _Block([fresh()])
        current.body.append(instruction)
        if instruction.opcode in _TERMINATORS:
            blocks.append(current)
            current = None

    if current is not None:
        blocks.append(current)

    # Turn implicit fallthrough edges into explicit jumps. A conditional
    # branch still needs its false (fallthrough) successor.
    for index, block in enumerate(blocks):
        last = block.body[-1].opcode if block.body else None
        if last not in _TERMINATORS:
            if index + 1 < len(blocks):
                block.body.append(TAC("jmp", [blocks[index + 1].labels[0]]))
            else:
                block.body.append(TAC("ret", []))

    return blocks


def _label_map(blocks: list[_Block]) -> dict[str, _Block]:
    return {label: block for block in blocks for label in block.labels}


def _successors(block: _Block, labels: dict[str, _Block]) -> list[_Block]:
    successors: list[_Block] = []
    for instruction in block.body:
        if instruction.opcode in JUMPS or instruction.opcode == "jmp":
            target = labels[str(instruction.arguments[-1])]
            if target not in successors:
                successors.append(target)
    return successors


def _remove_unreachable(blocks: list[_Block]) -> bool:
    if not blocks:
        return False

    labels = _label_map(blocks)
    reachable: set[_Block] = set()
    pending = [blocks[0]]
    while pending:
        block = pending.pop()
        if block in reachable:
            continue
        reachable.add(block)
        pending.extend(_successors(block, labels))

    old_length = len(blocks)
    blocks[:] = [block for block in blocks if block in reachable]
    return len(blocks) != old_length


def _thread_jumps(blocks: list[_Block]) -> bool:
    """Redirect branches through blocks containing only another jump."""

    labels = _label_map(blocks)
    changed = False

    def final_target(label: str) -> str:
        seen: set[str] = set()
        current = label
        while current not in seen:
            seen.add(current)
            block = labels[current]
            if len(block.body) != 1 or block.body[0].opcode != "jmp":
                break
            following = str(block.body[0].arguments[0])
            if following not in labels:
                break
            current = following
        return current

    for block in blocks:
        for instruction in block.body:
            if instruction.opcode in JUMPS or instruction.opcode == "jmp":
                old = str(instruction.arguments[-1])
                new = final_target(old)
                if new != old:
                    instruction.arguments[-1] = new
                    changed = True
    return changed


_SIGNS = frozenset((-1, 0, 1))
_JUMP_SIGNS = {
    "jz": frozenset((0,)),
    "jnz": frozenset((-1, 1)),
    "jl": frozenset((-1,)),
    "jnl": frozenset((0, 1)),
    "jle": frozenset((-1, 0)),
    "jnle": frozenset((1,)),
}


def _signs_on_edge(
    source: _Block,
    target: _Block,
    operand: str,
    labels: dict[str, _Block],
) -> frozenset[int]:
    """Possible signs of ``operand`` when the source-to-target edge is taken."""

    possible = _SIGNS
    reaching: set[int] = set()
    for instruction in source.body:
        if instruction.opcode in JUMPS:
            destination = labels[str(instruction.arguments[-1])]
            if instruction.arguments[0] == operand:
                taken = possible & _JUMP_SIGNS[instruction.opcode]
                if destination is target:
                    reaching.update(taken)
                possible = possible - _JUMP_SIGNS[instruction.opcode]
            elif destination is target:
                # This edge depends on another operand, so it tells us
                # nothing about the one being studied.
                reaching.update(possible)
        elif instruction.opcode == "jmp":
            if labels[str(instruction.arguments[0])] is target:
                reaching.update(possible)
            break
    return frozenset(reaching)


def _thread_conditions(blocks: list[_Block]) -> bool:
    """Fold a repeated sign/zero test when incoming edges determine it."""

    labels = _label_map(blocks)
    predecessors: dict[_Block, set[_Block]] = {block: set() for block in blocks}
    for predecessor in blocks:
        for successor in _successors(predecessor, labels):
            predecessors[successor].add(predecessor)

    for block in blocks:
        if not predecessors[block]:
            continue

        for index, instruction in enumerate(block.body):
            if instruction.opcode not in JUMPS:
                continue
            operand = instruction.arguments[0]

            # The fact learned on entry remains valid only if this block has
            # not assigned the tested temporary/global before reaching here.
            if any(previous.result == operand for previous in block.body[:index]):
                continue

            possible: set[int] = set()
            for predecessor in predecessors[block]:
                possible.update(_signs_on_edge(predecessor, block, operand, labels))
            if not possible:
                continue

            taken = _JUMP_SIGNS[instruction.opcode]
            if possible <= taken:
                block.body[index:] = [TAC("jmp", [instruction.arguments[-1]])]
                return True
            if possible.isdisjoint(taken):
                del block.body[index]
                return True

    return False


def _coalesce(blocks: list[_Block]) -> bool:
    """Merge a block with its sole successor when safe."""

    labels = _label_map(blocks)
    predecessors: dict[_Block, set[_Block]] = {block: set() for block in blocks}
    for block in blocks:
        for successor in _successors(block, labels):
            predecessors[successor].add(block)

    for block in blocks:
        if not block.body or block.body[-1].opcode != "jmp":
            continue
        target = labels[str(block.body[-1].arguments[0])]
        if target is block or predecessors[target] != {block}:
            continue
        # A set of predecessors loses edge multiplicity.  If an earlier
        # conditional in ``block`` also targets ``target``, its label must
        # remain in the middle of the merged instruction stream.  Our compact
        # representation stores labels only at block entries, so retain the
        # two blocks in that case.
        if any(
            instruction.opcode in JUMPS
            and labels[str(instruction.arguments[-1])] is target
            for instruction in block.body[:-1]
        ):
            continue

        block.body.pop()
        block.labels.extend(target.labels)
        block.body.extend(target.body)
        blocks.remove(target)
        return True
    return False


def _serialize(blocks: list[_Block]) -> list[TAC]:
    """Choose a block order and omit jumps made redundant by that order."""

    if not blocks:
        return []

    labels = _label_map(blocks)
    order: list[_Block] = []
    seen: set[_Block] = set()

    def visit(block: _Block) -> None:
        if block in seen:
            return
        seen.add(block)
        order.append(block)
        if block.body and block.body[-1].opcode == "jmp":
            visit(labels[str(block.body[-1].arguments[0])])
        for successor in _successors(block, labels):
            visit(successor)

    visit(blocks[0])
    for block in blocks:
        visit(block)

    result: list[TAC] = []
    for index, block in enumerate(order):
        following = order[index + 1] if index + 1 < len(order) else None
        instructions = list(block.body)

        if following is not None and len(instructions) >= 2:
            conditional, jump = instructions[-2:]
            if (
                conditional.opcode in JUMPS
                and jump.opcode == "jmp"
                and str(conditional.arguments[-1]) in following.labels
            ):
                instructions[-2] = TAC(
                    _INVERSE_JUMP[conditional.opcode],
                    [*conditional.arguments[:-1], jump.arguments[0]],
                    conditional.result,
                )
                instructions.pop()

        if (
            following is not None
            and instructions
            and instructions[-1].opcode == "jmp"
            and str(instructions[-1].arguments[0]) in following.labels
        ):
            instructions.pop()

        result.extend(TAC("label", [label]) for label in block.labels)
        result.extend(instructions)

    return result


def optimize(body: list[TAC]) -> list[TAC]:
    """Build, simplify, and serialize a procedure's control-flow graph."""

    blocks = _make_blocks(body)
    if not blocks:
        return []

    changed = True
    while changed:
        changed = _thread_jumps(blocks)
        changed = _thread_conditions(blocks) or changed
        changed = _remove_unreachable(blocks) or changed
        while _coalesce(blocks):
            changed = True

    return _serialize(blocks)
