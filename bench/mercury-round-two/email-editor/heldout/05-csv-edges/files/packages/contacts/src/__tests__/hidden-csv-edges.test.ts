import { describe, it, expect } from 'vitest';
import { parseCSV, detectDelimiter } from '../csv-importer';

describe('parseCSV', () => {
  it('ignores a byte order mark', () => {
    expect(parseCSV('﻿email,name\na@b.c,Al')).toEqual([
      ['email', 'name'],
      ['a@b.c', 'Al'],
    ]);
    expect(parseCSV('﻿"email",name')).toEqual([['email', 'name']]);
  });

  it('treats a bare carriage return as a row break', () => {
    expect(parseCSV('a,b\rc,d\re,f')).toEqual([
      ['a', 'b'],
      ['c', 'd'],
      ['e', 'f'],
    ]);
    expect(parseCSV('a,b\r\nc,d\re,f\ng,h')).toEqual([
      ['a', 'b'],
      ['c', 'd'],
      ['e', 'f'],
      ['g', 'h'],
    ]);
  });

  it('keeps a carriage return inside quotes', () => {
    expect(parseCSV('"line1\rline2",x')).toEqual([['line1\rline2', 'x']]);
    expect(parseCSV('"line1\r\nline2",x\ny,z')).toEqual([
      ['line1\r\nline2', 'x'],
      ['y', 'z'],
    ]);
  });

  it('keeps whitespace inside quotes', () => {
    expect(parseCSV('" padded ",x')).toEqual([[' padded ', 'x']]);
    expect(parseCSV('a," b"')).toEqual([['a', ' b']]);
    expect(parseCSV('"\ttab\t"')).toEqual([['\ttab\t']]);
  });

  it('drops whitespace around a quoted field', () => {
    expect(parseCSV('  "a"  ,  "b"')).toEqual([['a', 'b']]);
  });

  it('trims only the unquoted edges of a mixed field', () => {
    expect(parseCSV('  x "y z"  ,k')).toEqual([['x y z', 'k']]);
    expect(parseCSV('"a" b ,k')).toEqual([['a b', 'k']]);
    expect(parseCSV(' a "b " ')).toEqual([['a b ']]);
  });

  it('still trims unquoted fields and unescapes doubled quotes', () => {
    expect(parseCSV('  plain  , two words ')).toEqual([['plain', 'two words']]);
    expect(parseCSV('"say ""hi"" "')).toEqual([['say "hi" ']]);
  });

  it('keeps a row whose only content is quoted whitespace, drops truly empty rows', () => {
    expect(parseCSV('a,b\n" ",\n,\n\nc,d')).toEqual([
      ['a', 'b'],
      [' ', ''],
      ['c', 'd'],
    ]);
  });

  it('honors another delimiter', () => {
    expect(parseCSV('﻿a;" b ";c\rd;e;f', ';')).toEqual([
      ['a', ' b ', 'c'],
      ['d', 'e', 'f'],
    ]);
  });
});

describe('detectDelimiter', () => {
  it('ignores delimiters inside quotes', () => {
    expect(detectDelimiter('"Doe, John";age;city\n1,2,3,4,5')).toBe(';');
    expect(detectDelimiter('"a|b|c|d"\tx\ty')).toBe('\t');
  });

  it('ends the first line at a bare carriage return', () => {
    expect(detectDelimiter('a;b\rc,d,e,f')).toBe(';');
    expect(detectDelimiter('a|b\r\nc,d,e,f')).toBe('|');
  });

  it('does not end the first line at a line break inside quotes', () => {
    expect(detectDelimiter('"multi\nline, here";b;c\n1,2,3,4')).toBe(';');
  });

  it('ignores a byte order mark', () => {
    expect(detectDelimiter('﻿"a";b')).toBe(';');
  });

  it('breaks ties by candidate order and defaults to a comma', () => {
    expect(detectDelimiter('a,b;c')).toBe(',');
    expect(detectDelimiter('a;b|c')).toBe(';');
    expect(detectDelimiter('single')).toBe(',');
    expect(detectDelimiter('')).toBe(',');
  });
});
