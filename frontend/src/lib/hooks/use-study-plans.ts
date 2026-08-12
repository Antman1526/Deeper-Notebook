'use client'

import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'

import { QUERY_KEYS } from '@/lib/api/query-client'
import {
  AddStudyPlanSourceInput,
  ApproveStudySyllabusInput,
  CreateStudyPlanInput,
  ProposeStudySyllabusInput,
  RemoveStudyPlanSourceInput,
  SaveStudySyllabusInput,
  UpdateStudyPlanInput,
} from '@/lib/types/study-plans'
import { studyPlansApi } from '@/lib/api/study-plans'

export function useStudyPlans() {
  return useQuery({
    queryKey: QUERY_KEYS.studyPlans,
    queryFn: studyPlansApi.list,
  })
}

export function useStudyPlan(planId: string | null | undefined) {
  return useQuery({
    queryKey: QUERY_KEYS.studyPlan(planId ?? ''),
    queryFn: () => studyPlansApi.get(planId as string),
    enabled: Boolean(planId),
  })
}

export function useStudyPlanSources(planId: string | null | undefined) {
  return useQuery({
    queryKey: QUERY_KEYS.studyPlanSources(planId ?? ''),
    queryFn: () => studyPlansApi.get(planId as string),
    enabled: Boolean(planId),
    select: (plan) => plan.source_links,
  })
}

export function useStudyPlanReadiness(planId: string | null | undefined) {
  return useQuery({
    queryKey: QUERY_KEYS.studyPlanReadiness(planId ?? ''),
    queryFn: () => studyPlansApi.readiness(planId as string),
    enabled: Boolean(planId),
  })
}

export function useStudySyllabus(planId: string | null | undefined, version?: number) {
  return useQuery({
    queryKey: [...QUERY_KEYS.studySyllabus(planId ?? ''), version ?? 'active'] as const,
    queryFn: async () => {
      try {
        return await studyPlansApi.syllabus(planId as string, version)
      } catch (error) {
        const status = (error as { response?: { status?: number } })?.response?.status
        if (status === 404) return null
        throw error
      }
    },
    enabled: Boolean(planId),
  })
}

export function useCreateStudyPlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateStudyPlanInput) => studyPlansApi.create(input),
    onSuccess: async (plan) => {
      queryClient.setQueryData(QUERY_KEYS.studyPlan(plan.plan_id), plan)
      await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlans })
    },
  })
}

export function useUpdateStudyPlan() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: UpdateStudyPlanInput }) =>
      studyPlansApi.update(planId, input),
    onSuccess: async (plan) => {
      queryClient.setQueryData(QUERY_KEYS.studyPlan(plan.plan_id), plan)
      await queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlans })
    },
  })
}

export function useAddStudyPlanSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: AddStudyPlanSourceInput }) =>
      studyPlansApi.addSource(planId, input),
    onSuccess: async (_link, { planId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlans }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlan(planId) }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlanSources(planId) }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlanReadiness(planId) }),
      ])
    },
  })
}

export function useRemoveStudyPlanSource() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: RemoveStudyPlanSourceInput }) =>
      studyPlansApi.removeSource(planId, input),
    onSuccess: async (_result, { planId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlans }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlan(planId) }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlanSources(planId) }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlanReadiness(planId) }),
      ])
    },
  })
}

export function useProposeStudySyllabus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: ProposeStudySyllabusInput }) =>
      studyPlansApi.proposeSyllabus(planId, input),
    onSuccess: async (_syllabus, { planId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlans }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlan(planId) }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studySyllabus(planId) }),
      ])
    },
  })
}

export function useSaveStudySyllabus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: SaveStudySyllabusInput }) =>
      studyPlansApi.saveSyllabus(planId, input),
    onSuccess: async (_syllabus, { planId }) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlans }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlan(planId) }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studySyllabus(planId) }),
      ])
    },
  })
}

export function useApproveStudySyllabus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ planId, input }: { planId: string; input: ApproveStudySyllabusInput }) =>
      studyPlansApi.approveSyllabus(planId, input),
    onSuccess: async (plan, { planId }) => {
      queryClient.setQueryData(QUERY_KEYS.studyPlan(planId), plan)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studyPlans }),
        queryClient.invalidateQueries({ queryKey: QUERY_KEYS.studySyllabus(planId) }),
      ])
    },
  })
}
