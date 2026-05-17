// v0.7.105 — Filesystem listing API wrapper for the directory-picker UI.
// Mirrors api/routers/filesystem.py endpoints exposed at /api/fs/*.

import apiClient from './client'
import {
  FsHomeResponse,
  FsListFilter,
  FsListResponse,
  FsMkdirRequest,
  FsMkdirResponse,
} from '@/lib/types/api'

export interface FsListParams {
  path: string
  show_hidden?: boolean
  only?: FsListFilter
}

export const filesystemApi = {
  home: async () => {
    const response = await apiClient.get<FsHomeResponse>('/fs/home')
    return response.data
  },

  list: async (params: FsListParams) => {
    const response = await apiClient.get<FsListResponse>('/fs/list', {
      params: {
        path: params.path,
        show_hidden: params.show_hidden ?? false,
        only: params.only ?? 'all',
      },
    })
    return response.data
  },

  mkdir: async (data: FsMkdirRequest) => {
    const response = await apiClient.post<FsMkdirResponse>('/fs/mkdir', {
      path: data.path,
      parents: data.parents ?? true,
    })
    return response.data
  },
}
