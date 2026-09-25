import { test } from "node:test";
import assert from "node:assert/strict";
import { formatBytes } from "../../frontend/helpers.js";

const KB = 1024;
const MB = 1024 ** 2;
const GB = 1024 ** 3;
const TB = 1024 ** 4;

test("formatBytes shows a dash for a missing value", () => {
    assert.equal(formatBytes(null), "-");
    assert.equal(formatBytes(undefined), "-");
});

test("formatBytes shows whole bytes below 1 KB", () => {
    assert.equal(formatBytes(0), "0 B");
    assert.equal(formatBytes(1023), "1023 B");
});

test("formatBytes rounds KB and MB up to whole numbers", () => {
    assert.equal(formatBytes(KB), "1 KB");
    assert.equal(formatBytes(1.2 * KB), "2 KB");
    assert.equal(formatBytes(MB), "1 MB");
    assert.equal(formatBytes(733.4 * MB), "734 MB");
});

test("formatBytes shows GB and TB with one decimal", () => {
    assert.equal(formatBytes(GB), "1.0 GB");
    assert.equal(formatBytes(68.34 * GB), "68.3 GB");
    assert.equal(formatBytes(TB), "1.0 TB");
    assert.equal(formatBytes(1691.1 * GB), "1.7 TB");
});

test("formatBytes moves a value that rounds to 1024 to the next unit", () => {
    assert.equal(formatBytes(1023.5 * KB), "1 MB");
    assert.equal(formatBytes(1023.5 * MB), "1.0 GB");
    assert.equal(formatBytes(1023.96 * GB), "1.0 TB");
});

test("formatBytes stays in TB above 1024 TB", () => {
    assert.equal(formatBytes(2048 * TB), "2048.0 TB");
});
