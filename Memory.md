# Memory: sizes, words, and how Lisp data is stored

Genera reports memory in *words*, not bytes. This file explains what a
word is, how much memory the system can be given, and how the common
Lisp objects are laid out.

The facts about data layout come from Genera's own system definitions
(`sys.sct/i-sys/sysdef.lisp`) and from the emulator source. The memory
limits were measured by booting this emulator.

## The word

The machine Genera runs on, the Symbolics Ivory, has a **40-bit word**.
Every word of memory has the same shape:

    bits 39-38   cdr code    2 bits   how lists are packed (see below)
    bits 37-32   data type   6 bits   what kind of object this is
    bits 31-0    data       32 bits   an address, or the value itself

The top 8 bits together are called the *tag*. Because every word
carries its own type, the machine checks types as it runs; there is no
untyped memory.

- Memory is addressed by word, not by byte. An address is 32 bits, so
  the address space is 2^32 words (4096 megawords).
- This emulator keeps each word as a 4-byte data part and a 1-byte tag,
  so **one word costs 5 bytes** of host memory.
- "M words" in Genera's messages means 2^20 words (1,048,576).

Converting:

    megabytes on the host  =  megawords x 5
    megawords              =  megabytes / 5

So the `2048` in `genera.virtualMemory: 2048` is 409.6 megawords, which
is what Genera prints at boot.

Pages: an Ivory page is 256 words. The emulator manages host memory in
units of 8192 words (40 kilobytes).

## How much memory the system supports

The size is set with `genera.virtualMemory` in `.VLM`, or `-vm` on the
command line, in megabytes (see `VLM.md`). It is the total for the
emulated machine, including the world that is loaded.

| | Megabytes | Megawords |
|---|---|---|
| Minimum | 125 | 25.0 |
| Default | 200 | 40.0 |
| Largest that Genera reports correctly | 10239 | 2047.8 |
| Arithmetic ceiling | 20480 | 4096 |

**Minimum.** The emulator refuses anything below 125 ("Minimum virtual
memory size is 125 megabytes"). At 125 the distribution world boots
with 14.4 megawords free. The emulator also warns when the size is
less than twice the world's size.

**Maximum.** The emulator enforces no upper limit. The limits come from
32-bit arithmetic:

- Genera holds the size as a signed 32-bit count of words. From 10240
  megabytes (2^31 words) upward that count is negative, and the boot
  message shows a negative request.
- At 20480 megabytes the count is 2^32 words, the size of the whole
  Ivory address space, and wraps to zero.

Use **10239 or less**. Above that Genera still boots and still counts
more free space, but its own figures are wrong and it has not been
shown that the extra memory can be used.

Measured on this emulator with the distribution world. Each line is one
boot; the last two columns are what Genera printed.

| `-vm` | "virtual memory requested" | "still available" |
|---|---|---|
| 124 | refused by the emulator | |
| 125 | 25.0M words | 14.4M words |
| 2048 | 409.6M words | 399.0M words |
| 4096 | 819.2M words | about 808.6M words |
| 8192 | 1638.4M words | 1627.8M words |
| 10239 | 2047.8M words | 2037.2M words |
| 10240 | -2048.0M words | 2037.4M words |
| 16000 | -896.0M words | 3189.4M words |

These tests only booted Genera and read the banner. They did not fill
the memory, so they show what Genera accepts, not that every megaword
can be allocated. Part of the 4096-megaword address space is also
reserved for the system's own areas (stacks, wired storage), so the
usable total is below the arithmetic ceiling in any case.

**What it costs the host.** The setting reserves address space, not
memory. Linux commits real memory only for the words Genera has
touched: an idle distribution world uses about 75 megabytes whatever
the setting. A Lisp program that really fills its memory needs 5 bytes
of host RAM or swap per word.

**Choosing a value.** 2048 is comfortable for general use. The original
Open Genera manual says that when Lisp runs out, Genera stops in the
VLM debugger and may be continued with a 25% larger limit; that has not
been tried on this port.

## How Lisp data is stored

Objects are of two kinds. An *immediate* object fits in the 32 data
bits of the word that refers to it and takes no other storage. A
*pointer* object's word holds the address of storage elsewhere.

### Integers

| Kind | Storage | Range |
|---|---|---|
| fixnum | immediate, 32 bits two's complement | -2,147,483,648 to 2,147,483,647 |
| bignum | pointer to a header word and as many 32-bit words as needed | unlimited |

Arithmetic moves between the two automatically. Fixnums take no
storage and are never garbage; bignums are allocated.

### Floating point

| Kind | Storage | Format |
|---|---|---|
| single-float | immediate, 32 bits | IEEE single precision |
| double-float | pointer to 2 words (high half, low half) | IEEE double precision |

Single floats cost nothing to create. Each new double float allocates
two words.

### Other numbers

| Kind | Storage |
|---|---|
| small ratio | immediate: 16-bit numerator, 16-bit denominator |
| big ratio | pointer to 2 words: numerator, denominator |
| complex | pointer to 2 words: real part, imaginary part |

### Characters

A character is immediate: the character code and its style and
modifier bits fit in the 32 data bits.

### Conses and lists

A cons is two cells, **car** and **cdr**, and normally takes **2
words**. The 2-bit cdr code in the car's word says how to find the cdr:

| Cdr code | Meaning |
|---|---|
| cdr-normal | the cdr is in the next word (the ordinary 2-word cons) |
| cdr-next | the cdr *is* the next word's cons; nothing is stored for it |
| cdr-nil | the cdr is NIL; nothing is stored for it |

The last two are *cdr-coding*. A list built in one piece (by `list`,
`make-list`, `copy-list`, or the reader, or after the garbage collector
has copied it) is stored as consecutive words, one per element: every
word is cdr-next except the last, which is cdr-nil.

    list of n elements, cdr-coded        n words
    list of n elements, built by cons   2n words

Changing the cdr of a cdr-coded cell with `rplacd` still works: the
system replaces the cell with an invisible forwarding pointer to a new
2-word cons.

### Symbols

A symbol is 5 words: print name, value, function, property list, and
package. `NIL` has its own data type but is otherwise a symbol.

### Arrays and strings

An array is a header word followed by its elements. The header gives
the element type and how many elements are packed in each word.

| Elements | Per word |
|---|---|
| general Lisp objects | 1 |
| ordinary characters (a string) | 4 |
| bits | 32 |
| other small integers | 2, 4, 8 or 16, by size |

So a 100-character string is 1 header word plus 25 data words. Arrays
with more than 32,767 elements, with a fill pointer or leader, or with
several dimensions have a longer header.

### Code

Compiled functions are stored as words too. The instruction set packs
two 18-bit instructions into one 40-bit word, using part of the tag, so
compiled code is about two instructions per word.

## Seeing it for yourself

In a Lisp Listener:

    Show Machine Configuration        memory figures for this boot
    (room)                            what each area of memory holds
    (sys:%data-type 'foo)             the data type number of an object
    most-positive-fixnum              2147483647

`docs/Internals.pdf` describes storage management and the garbage
collector in depth.
