"""Player inventory state and terminal-friendly formatting."""


class Inventory:
    def __init__(self, base=16):
        self.capacity = base
        self.slots = {}

    def add(self, item, count=1):
        if item not in self.slots and len(self.slots) >= self.capacity:
            self.capacity *= 2
        self.slots[item] = self.slots.get(item, 0) + count

    def has(self, requirements):
        return all(self.slots.get(item, 0) >= count for item, count in requirements.items())

    def consume(self, requirements):
        if not self.has(requirements):
            return False
        for item, count in requirements.items():
            remaining = self.slots[item] - count
            if remaining:
                self.slots[item] = remaining
            else:
                del self.slots[item]
        return True

    def compact(self):
        if not self.slots:
            return f"[0/{self.capacity}] empty"
        contents = " ".join(f"{item}:{count}" for item, count in self.slots.items())
        return f"[{len(self.slots)}/{self.capacity}] {contents}"

    def full_lines(self):
        if not self.slots:
            return [f"capacity {self.capacity} — empty. gather with 'e' near a resource."]
        lines = [f"capacity: {len(self.slots)}/{self.capacity}"]
        return lines + [f"  {item}: {count}" for item, count in self.slots.items()]
