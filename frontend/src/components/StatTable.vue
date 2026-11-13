<script setup>
// A compact stats table: columns are [{ key, label, format }], an optional
// footer row (e.g. career totals) is rendered in bold.
import { formatValue, isNumeric } from '../format'

defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, required: true },
  footer: { type: Object, default: null },
  footerLabel: { type: String, default: 'Career' },
  rowKey: { type: Function, default: (r, i) => i },
})
</script>

<template>
  <div class="table-wrap">
    <table class="data">
      <thead>
        <tr>
          <th v-for="c in columns" :key="c.key" :class="{ num: isNumeric(c.format) }" :title="c.title">{{ c.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rows" :key="rowKey(r, i)">
          <td v-for="c in columns" :key="c.key" :class="{ num: isNumeric(c.format) }">
            {{ formatValue(r[c.key], c.format) }}
          </td>
        </tr>
      </tbody>
      <tfoot v-if="footer">
        <tr>
          <td v-for="(c, j) in columns" :key="c.key" :class="{ num: isNumeric(c.format) }">
            {{ j === 0 ? footerLabel : formatValue(footer[c.key], c.format) }}
          </td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>
